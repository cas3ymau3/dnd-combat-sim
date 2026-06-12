"""
content.py — the declarative ability layer: load YAML abilities and translate
their `effect`/`cost` blocks into the engine objects the existing decision
points already consume.

Design contract (CLAUDE.md #1/#2, design/ability_schema.md):
  An ability is DATA (trigger / effect / cost).  The engine is a generic
  interpreter of that data — adding an ability should mean writing YAML, not
  Python.  Combat POLICY (which ability fires, in what order, how shared
  resources are arbitrated) stays Python.

What this module is — and is NOT
--------------------------------
The engine never built a generic "verb VM".  It built a fixed set of TYPED
decision points (Policy.decide / on_hit / on_miss / on_incoming_hit /
on_failed_save) that return hand-shaped response objects (Choice, HitResponse,
Modifier, …).  So the declarative layer is an ADAPTER ("effect compiler"): given
ONE ability's data, it produces the response FIELDS the policy would otherwise
hand-build.  It does not roll dice, read game state, or decide anything — those
stay in the engine (resolution) and the policy (decisions) respectively.

The boundary (confirmed this session): the interpreter translates one ability's
effect+cost into Modifiers / rider dice / action-economy + a resource *type*;
the build's Python policy still decides WHICH ability fires and resolves the
abstract resource type to a concrete slot (e.g. spell_slot → free_cast).

Coverage so far (intentionally narrow — grown against the War Angel oracle):
  - `apply_modifier`  with hooks `bonus_die` (Bless +1d4) and `flat`  → Modifier
  - `damage` on-hit rider (Wrathful Smite 1d6)                        → HitRiderSpec
Anything outside this raises NotImplementedError LOUDLY rather than silently
dropping it — surfacing schema/engine gaps cheaply is the whole point of doing
this against a validated build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .modifiers import Modifier

# Repo-root/content/abilities — content.py lives in src/, so parents[1] is root.
_CONTENT_DIR = Path(__file__).resolve().parents[1] / "content" / "abilities"

# A dice expression like "1d6" or "2d8".
_DICE_RE = re.compile(r"^\s*(\d+)d(\d+)\s*$")


def parse_dice(expr: str) -> tuple[int, int]:
    """Parse a dice expression string into the engine's (count, sides) tuple.

    "1d6" → (1, 6), "2d8" → (2, 8).  Raises ValueError on anything else so a
    malformed content string fails loudly at load/interpret time, not silently.
    """
    m = _DICE_RE.match(expr)
    if not m:
        raise ValueError(f"parse_dice: not a 'NdM' dice expression: {expr!r}")
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# Ability — a parsed, validated content object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Ability:
    """One declarative ability, parsed from YAML.

    Mirrors the schema's three layers (trigger / effect / cost) plus the
    top-level name/tags/duration.  `raw` keeps the full parsed dict so future
    interpreters can reach fields this slice doesn't model yet.
    """

    name: str
    tags: tuple[str, ...]
    trigger: dict | None
    effect: list | dict
    cost: dict | None
    duration: dict | None
    raw: dict

    @classmethod
    def from_dict(cls, doc: dict) -> "Ability":
        if "name" not in doc:
            raise ValueError(f"ability document has no 'name': {doc!r}")
        return cls(
            name=doc["name"],
            tags=tuple(doc.get("tags", []) or []),
            trigger=doc.get("trigger"),
            effect=doc.get("effect", []),
            cost=doc.get("cost"),
            duration=doc.get("duration"),
            raw=doc,
        )


def load_abilities(directory: "Path | str | None" = None) -> dict[str, Ability]:
    """Load every ability from the content directory into a name → Ability map.

    Each YAML file is a multi-document stream (``---``-separated).  Names are
    unique across the whole corpus; a collision raises (it's a content bug).
    """
    directory = Path(directory) if directory is not None else _CONTENT_DIR
    library: dict[str, Ability] = {}
    for path in sorted(directory.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as fh:
            for doc in yaml.safe_load_all(fh):
                if not doc:                      # skip empty / comment-only docs
                    continue
                ability = Ability.from_dict(doc)
                if ability.name in library:
                    raise ValueError(
                        f"duplicate ability name {ability.name!r} "
                        f"(second definition in {path.name})"
                    )
                library[ability.name] = ability
    return library


# ---------------------------------------------------------------------------
# Effect interpreter — apply_modifier → Modifier
# ---------------------------------------------------------------------------

# `applies_to` is an ABSTRACT scope in the schema (e.g. "attack rolls and saving
# throws").  The engine has concrete stat keys.  This default maps the scope to
# the stats the engine actually ROLLS DICE for — attack_bonus (every attack) and
# con_save (concentration).  Those are literally the only two stats roll_dice()
# is ever invoked on, so a bonus_die on any other save is DPR-inert; the build
# may inject a wider map once more saves are rolled.
DEFAULT_SCOPE_MAP: dict[str, tuple[str, ...]] = {
    "attack_rolls_and_saving_throws": ("attack_bonus", "con_save"),
}


def _resolve_stats(block: dict, scope_map: dict[str, tuple[str, ...]]) -> list[str]:
    """Resolve a modifier block's target stat(s).

    A block names either a concrete `stat:` (e.g. flat AC) or an abstract
    `applies_to:` scope that the scope_map expands to concrete engine stats.
    """
    if "stat" in block:
        return [block["stat"]]
    scope = block.get("applies_to")
    if scope in scope_map:
        return list(scope_map[scope])
    raise NotImplementedError(
        f"interpret_modifiers: unresolved stat scope {scope!r} "
        f"(add it to scope_map or give the block an explicit 'stat')"
    )


def interpret_modifiers(
    ability: Ability,
    source: str | None = None,
    scope_map: dict[str, tuple[str, ...]] | None = None,
) -> list[Modifier]:
    """Translate an ability's `apply_modifier` effect block(s) into Modifiers.

    Supports the two hooks the current builds need:
      - `bonus_die` → Modifier(stat, value=0, source, dice=(n, sides))   (Bless)
      - `flat`      → Modifier(stat, value=N, source)                    (SoF, MW)

    `source` defaults to the ability name; pass it explicitly when the engine
    removes the modifier by a different key (e.g. "bless").  One Modifier is
    produced per resolved stat (Bless → attack_bonus + con_save).
    """
    scope_map = scope_map if scope_map is not None else DEFAULT_SCOPE_MAP
    source = source if source is not None else ability.name

    if not isinstance(ability.effect, list):
        raise NotImplementedError(
            f"interpret_modifiers({ability.name}): expected an effect list, got "
            f"{type(ability.effect).__name__} (choose_one not supported here)"
        )

    mods: list[Modifier] = []
    for block in ability.effect:
        verb = block.get("verb")
        if verb != "apply_modifier":
            raise NotImplementedError(
                f"interpret_modifiers({ability.name}): verb {verb!r} is not an "
                f"apply_modifier (this interpreter only builds Modifiers)"
            )
        hook = block.get("hook")
        for stat in _resolve_stats(block, scope_map):
            if hook == "bonus_die":
                mods.append(
                    Modifier(stat, 0, source, dice=parse_dice(block["die"]))
                )
            elif hook == "flat":
                mods.append(Modifier(stat, block["value"], source))
            else:
                raise NotImplementedError(
                    f"interpret_modifiers({ability.name}): modifier hook "
                    f"{hook!r} not yet supported"
                )
    return mods


# ---------------------------------------------------------------------------
# Effect interpreter — on-hit damage rider → HitRiderSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HitRiderSpec:
    """The data-derived pieces of an on-hit rider (e.g. Wrathful Smite).

    The policy combines this with its own arbitration: it resolves
    `resource_type`/`min_level` to a concrete slot (slot priority is build
    logic) and decides whether to fire at all.  The interpreter only states
    WHAT the ability does — the dice it adds and what action economy it costs.

    Fields
    ------
    extra_damage_dice:
        Dice added to the hit's damage, e.g. [(1, 6)] — fold into
        HitResponse.extra_damage_dice (they double on a crit like any others).
    action_cost:
        The action-economy slot the rider consumes ("bonus_action" for Wrathful
        Smite) or None.
    resource_type / min_level:
        The ABSTRACT resource the rider needs (e.g. "spell_slot", min level 1).
        The policy maps this to a concrete pool; None when the ability is free.
    """

    extra_damage_dice: list[tuple[int, int]]
    action_cost: str | None
    resource_type: str | None = None
    min_level: int | None = None


def interpret_hit_rider(ability: Ability) -> HitRiderSpec:
    """Translate an on-hit `damage` rider ability into a HitRiderSpec.

    Reads the `damage` verb's dice (base form only for now) and the cost block's
    action economy + resource type.  Scaling (`increment`/upcast) is not yet
    modeled — it raises so the gap surfaces loudly rather than silently dropping
    upcast dice.
    """
    if not isinstance(ability.effect, list):
        raise NotImplementedError(
            f"interpret_hit_rider({ability.name}): expected an effect list"
        )

    dice: list[tuple[int, int]] = []
    for block in ability.effect:
        verb = block.get("verb")
        if verb != "damage":
            raise NotImplementedError(
                f"interpret_hit_rider({ability.name}): verb {verb!r} not "
                f"supported (this interpreter only builds damage riders)"
            )
        spec = block.get("dice")
        if isinstance(spec, dict):
            if "increment" in spec:
                raise NotImplementedError(
                    f"interpret_hit_rider({ability.name}): scaling/upcast dice "
                    f"('increment') not yet modeled"
                )
            base = spec["base"]
        else:
            base = spec
        dice.append(parse_dice(base))

    cost = ability.cost or {}
    resource = cost.get("resource") or {}
    return HitRiderSpec(
        extra_damage_dice=dice,
        action_cost=cost.get("action_economy"),
        resource_type=resource.get("type"),
        min_level=resource.get("min_level"),
    )
