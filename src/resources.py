"""
resources.py — ResourcePool: persistent limited-use resource tracking.

Design contract:
  - ResourcePool lives on Entity and tracks everything that isn't turn-level
    action economy (spell slots, ki, war priest charges, channel divinity, etc.).
  - Turn-level resources (action, bonus_action, reaction) are managed separately
    by the Scheduler and are NOT stored here.
  - Long rest always restores everything to maximum.
  - Short rest restores resources according to their sr_restore field:
      0        → no SR restore (long rest only)
      "full"   → fully restored on SR (e.g. pact magic slot, action surge)
      int > 0  → that many uses restored on SR (e.g. channel divinity +1/SR)
  - Spell slots use the naming convention "spell_slot_1" … "spell_slot_9".
    find_spell_slot(min_level) returns the name of the lowest available slot
    at or above the requested level — the canonical way for policies to pick
    which slot to spend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ResourceEntry
# ---------------------------------------------------------------------------

@dataclass
class ResourceEntry:
    """One limited-use resource pool.

    Parameters
    ----------
    current:
        Current available uses.
    maximum:
        Cap; restored to this on long rest (and on SR when sr_restore="full").
    sr_restore:
        Uses restored on a short rest (or Prayer of Healing SR-equivalent):
          0       — long rest only
          "full"  — fully restored
          int > 0 — that many uses added (e.g. Channel Divinity +1/SR)
    """
    current: int
    maximum: int
    sr_restore: int | Literal["full"] = 0


# ---------------------------------------------------------------------------
# ResourcePool
# ---------------------------------------------------------------------------

class ResourcePool:
    """All persistent resources for one entity.

    Construct with a dict of name → ResourceEntry.  Missing names return 0
    from available() so callers never need to guard for key absence.

    Usage
    -----
    pool = ResourcePool({
        "spell_slot_1": ResourceEntry(current=4, maximum=4, sr_restore=0),
        "spell_slot_2": ResourceEntry(current=3, maximum=3, sr_restore=0),
        "pact_magic_slot": ResourceEntry(current=1, maximum=1, sr_restore="full"),
        "channel_divinity": ResourceEntry(current=2, maximum=2, sr_restore=1),
        "action_surge": ResourceEntry(current=1, maximum=1, sr_restore="full"),
        "war_priest": ResourceEntry(current=3, maximum=3, sr_restore="full"),
        "brutality": ResourceEntry(current=4, maximum=4, sr_restore="full"),
    })
    pool.consume("spell_slot_2")       # True; current goes 3→2
    pool.restore_sr()                  # pact_magic_slot, action_surge, war_priest,
                                       # brutality fully restored; channel_divinity +1
    pool.restore_lr()                  # everything → maximum
    """

    def __init__(self, entries: dict[str, ResourceEntry] | None = None) -> None:
        self._entries: dict[str, ResourceEntry] = dict(entries or {})

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def available(self, name: str) -> int:
        """Current count for *name* (0 if resource not in pool)."""
        entry = self._entries.get(name)
        return entry.current if entry else 0

    def maximum(self, name: str) -> int:
        """Maximum count for *name* (0 if resource not in pool)."""
        entry = self._entries.get(name)
        return entry.maximum if entry else 0

    def as_dict(self) -> dict[str, int]:
        """Flat {name: current} dict for merging into GameState.resources."""
        return {name: e.current for name, e in self._entries.items()}

    def find_spell_slot(self, min_level: int) -> str | None:
        """Name of the lowest available slot at or above *min_level*.

        Returns None if no slot is available.  Policies call this when
        deciding which slot level to spend (e.g. for Divine Smite, wrathful
        smite, magic weapon).

        Example
        -------
        slot = actor.resources.find_spell_slot(2)   # "spell_slot_2" or higher
        if slot:
            choices.append(Choice(..., resource_cost={slot: 1}))
        """
        for level in range(min_level, 10):
            name = f"spell_slot_{level}"
            if self.available(name) > 0:
                return name
        return None

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def consume(self, name: str, amount: int = 1) -> bool:
        """Reduce *name* by *amount*.  Returns False (no-op) if insufficient."""
        entry = self._entries.get(name)
        if entry is None:
            log.warning("consume() called on unknown resource %r — ignored", name)
            return False
        if entry.current < amount:
            log.warning(
                "consume(%r, %d) failed — only %d/%d available",
                name, amount, entry.current, entry.maximum,
            )
            return False
        entry.current -= amount
        log.debug("consume(%r, %d) → %d/%d", name, amount, entry.current, entry.maximum)
        return True

    def restore(self, name: str, amount: int | Literal["full"] = "full") -> None:
        """Credit *name* by *amount* (clamped to maximum).

        Useful for out-of-combat actions like Prayer of Healing that restore
        specific resources without triggering a full SR.
        """
        entry = self._entries.get(name)
        if entry is None:
            return
        if amount == "full":
            entry.current = entry.maximum
        else:
            entry.current = min(entry.maximum, entry.current + amount)
        log.debug("restore(%r) → %d/%d", name, entry.current, entry.maximum)

    def add(self, name: str, entry: "ResourceEntry") -> None:
        """Install a resource entry, replacing any existing one of that name.

        Used by builds assembling a pool incrementally (e.g. attaching Hit Dice
        after construction), not during combat — nothing in resolution creates a
        resource."""
        self._entries[name] = entry

    def restore_sr(self) -> None:
        """Apply a short rest (or SR-equivalent like Prayer of Healing).

        Resources with sr_restore=0 are untouched.
        Resources with sr_restore="full" are restored to maximum.
        Resources with sr_restore=N have N uses added (clamped to maximum).
        """
        for name, entry in self._entries.items():
            if entry.sr_restore == 0:
                continue
            before = entry.current
            if entry.sr_restore == "full":
                entry.current = entry.maximum
            else:
                entry.current = min(entry.maximum, entry.current + entry.sr_restore)
            log.debug(
                "SR restore %r: %d → %d/%d",
                name, before, entry.current, entry.maximum,
            )

    def restore_lr(self) -> None:
        """Apply a long rest: all resources restored to maximum."""
        for name, entry in self._entries.items():
            entry.current = entry.maximum
        log.debug("LR restore: all resources at maximum")

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        parts = ", ".join(
            f"{name}={e.current}/{e.maximum}"
            for name, e in self._entries.items()
        )
        return f"ResourcePool({parts})"


# ---------------------------------------------------------------------------
# The spend/record PAIR (s62)
# ---------------------------------------------------------------------------

def spend_recorded(pool: "ResourcePool", name: str, amount: int = 1, *,
                   telemetry=None) -> bool:
    """Consume *amount* of *name* AND record it in the §13 economy channel.

    Why this exists, and why it is a function rather than a convention: spending a
    resource is a TWO-CALL SEQUENCE — ``pool.consume(name, amount)`` followed by
    ``telemetry.record_resource(name, amount)`` — and the scheduler performed both
    at its six call sites while every out-of-combat caller performed only the first.
    The channel therefore had TWO WRITERS and reported ONE of them, so
    ``spell_slots_per_day`` read 1.022 against 9.908 actually spent at War Angel L13
    (a 9.7x undercount) and ``limited_resources_per_day`` missed every Hit Die and
    every daily-plan Channel Divinity. Both metrics' declared definitions say "per
    adventuring day" without qualification, so both were false as implemented.

    This is the s54 seam lesson applied to a sequence rather than to a number: when
    an ordering must always hold, extract it so both callers share it instead of
    trusting each site to remember. The enforcement is
    ``test_every_resource_spend_reaches_the_economy_channel``, which asserts the
    invariant end to end — a guard, unlike a convention, that cannot go stale.

    ``telemetry`` is duck-typed (anything with ``record_resource``) to keep this
    module free of a telemetry import, and ``None`` is legal: a caller with no
    accumulator in scope still spends correctly, it simply records nothing. Nothing
    is recorded when the consume FAILS, so a refused spend cannot inflate the
    channel. The return value is ``consume``'s, because callers branch on it
    (``silvertail`` spends a slot inside an ``and`` chain).
    """
    ok = pool.consume(name, amount)
    if ok and telemetry is not None:
        telemetry.record_resource(name, amount)
    return ok
