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
  - `apply_status` (target mastery / self status) + flat `damage`     → OnHitEffectSpec
    (Brutality bluff = vex + advantage_next_save; bleed = sap + CHA flat)
  - `intercept_event` flat AC bump (Flourish Parry +CHA)              → InterceptSpec
  - flat attack-roll rescue (Guided Strike +10, on_miss)              → RollBonusSpec
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
    context: dict[str, int] | None = None,
) -> list[Modifier]:
    """Translate an ability's `apply_modifier` effect block(s) into Modifiers.

    Supports the two hooks the current builds need:
      - `bonus_die` → Modifier(stat, value=0, source, dice=(n, sides))   (Bless)
      - `flat`      → Modifier(stat, value=N, source)                    (SoF, MW)

    A `flat` block's value is either a literal `value: N` (Shield of Faith +2 AC)
    or a runtime `amount:` resolved against `context` (Magic Weapon's +1/+2 cast
    tier, supplied by the policy that decided which slot to spend).

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
                value = (
                    block["value"] if "value" in block
                    else _resolve_amount(block, context, ability.name)
                )
                mods.append(Modifier(stat, value, source))
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


# ---------------------------------------------------------------------------
# Effect interpreter — on-hit statuses + flat damage → OnHitEffectSpec
# ---------------------------------------------------------------------------

# The weapon masteries the engine actually implements (apply_masteries_on_hit).
# A TARGET-applied `apply_status` whose name is one of these becomes the hit's
# extra mastery; anything else routed at the target raises (the engine has no
# field for a generic on-hit target status yet — surfacing that gap is the point).
ENGINE_MASTERIES: frozenset[str] = frozenset({"sap", "vex"})


@dataclass(frozen=True)
class OnHitEffectSpec:
    """The data-derived pieces of an on-hit status/flat-damage effect (Brutality).

    The policy combines this with its own arbitration (which mode fires, whether
    the brutality charge is actually spent) and maps the fields onto whichever
    engine seam is in play — a `HitResponse` (bluff, on our own hit) or a
    `CounterSpec` (bleed, on the Flourish Counter).

    Fields
    ------
    target_masteries:
        Weapon masteries applied to the creature hit, e.g. ["vex"] (bluff) or
        ["sap"] (bleed) — fold into HitResponse.extra_masteries or
        CounterSpec.masteries.
    self_statuses:
        Statuses applied to the ATTACKER on this hit, e.g. ["advantage_next_save"]
        (bluff's save-advantage half) — map to HitResponse.self_status_on_hit.
    extra_flat_damage:
        Flat phase-5 damage added on the hit, e.g. +CHA mod (bleed).  Does NOT
        scale on a crit — fold into HitResponse/CounterSpec.extra_flat_damage.
    """

    target_masteries: list[str]
    self_statuses: list[str]
    extra_flat_damage: int = 0


def _resolve_amount(block: dict, context: dict[str, int] | None, ability_name: str) -> int:
    """Resolve a block's runtime `amount` against a policy-supplied context.

    The data states an ABSTRACT amount whose concrete value the policy provides
    at fire-time via `context`.  Two forms, both a lookup into `context`:
      - `amount: {ability_modifier: charisma}`  → context["charisma"]  (bleed +CHA)
      - `amount: {context: magic_weapon_bonus}` → context["magic_weapon_bonus"]
        (Magic Weapon's +1/+2 cast tier — which tier was cast is policy arbitration)

    This is the interpreter's runtime-dependent path: it EVALUATES against a
    context rather than compiling a constant, yet stays pure (data + context in →
    int out; no policy state leaks in).
    """
    amount = block.get("amount")
    if isinstance(amount, dict) and "ability_modifier" in amount:
        key = amount["ability_modifier"]
    elif isinstance(amount, dict) and "context" in amount:
        key = amount["context"]
    else:
        raise NotImplementedError(
            f"{ability_name}: runtime amount needs `{{ability_modifier: <stat>}}` "
            f"or `{{context: <key>}}`; got {amount!r}"
        )
    if context is None or key not in context:
        raise ValueError(
            f"{ability_name}: no value for amount key {key!r} in context {context!r}"
        )
    return context[key]


def interpret_on_hit_effects(
    ability: Ability,
    context: dict[str, int] | None = None,
) -> OnHitEffectSpec:
    """Translate an on-hit `apply_status` + flat-`damage` ability into a spec.

    Handles the two Brutality modes:
      - `apply_status` routed by `target`: a TARGET status that names a known
        weapon mastery → `target_masteries`; a SELF status → `self_statuses`.
      - flat `damage` (`amount: {ability_modifier: <stat>}`) → `extra_flat_damage`,
        resolved against `context` (e.g. {"charisma": cha_mod}).

    Raises loudly on anything outside this (a target status that is not a known
    mastery, a damage verb without a flat `amount`, an unknown verb) so the
    schema/engine gap surfaces rather than being silently dropped.
    """
    if not isinstance(ability.effect, list):
        raise NotImplementedError(
            f"interpret_on_hit_effects({ability.name}): expected an effect list "
            f"(choose_one not supported here)"
        )

    target_masteries: list[str] = []
    self_statuses: list[str] = []
    extra_flat_damage = 0

    for block in ability.effect:
        verb = block.get("verb")
        if verb == "apply_status":
            status = block["status"]
            target = block.get("target")
            if target == "self":
                self_statuses.append(status)
            elif target == "target":
                if status not in ENGINE_MASTERIES:
                    raise NotImplementedError(
                        f"interpret_on_hit_effects({ability.name}): target status "
                        f"{status!r} is not a known weapon mastery "
                        f"{sorted(ENGINE_MASTERIES)} — the engine has no field for "
                        f"a generic on-hit target status yet"
                    )
                target_masteries.append(status)
            else:
                raise NotImplementedError(
                    f"interpret_on_hit_effects({ability.name}): apply_status needs "
                    f"target 'self' or 'target'; got {target!r}"
                )
        elif verb == "damage":
            extra_flat_damage += _resolve_amount(block, context, ability.name)
        else:
            raise NotImplementedError(
                f"interpret_on_hit_effects({ability.name}): verb {verb!r} not "
                f"supported by this interpreter"
            )

    return OnHitEffectSpec(
        target_masteries=target_masteries,
        self_statuses=self_statuses,
        extra_flat_damage=extra_flat_damage,
    )


# ---------------------------------------------------------------------------
# Effect interpreter — flat attack-roll rescue → RollBonusSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RollBonusSpec:
    """The data-derived pieces of a flat attack-roll-bonus rescue (Guided Strike).

    The policy keeps the decision (greedy, never on an AoO, only when the bonus
    actually flips the miss) and maps the abstract resource to a concrete pool;
    the interpreter states WHAT — the flat bonus added to the roll and its cost.

    Fields
    ------
    bonus:
        Flat bonus added to the attack roll (Guided Strike = +10).
    resource_type / count:
        The resource the rescue consumes (channel_divinity, 1).
    """

    bonus: int
    resource_type: str | None = None
    count: int = 1


def interpret_roll_bonus(ability: Ability) -> RollBonusSpec:
    """Translate a flat attack-roll-bonus ability (Guided Strike) into a spec.

    Reads a single `apply_modifier flat` block targeting `attack_roll` (the +10)
    and the cost block's resource.  Raises loudly on anything else (a non-flat
    hook, a different stat, multiple blocks).
    """
    if not isinstance(ability.effect, list):
        raise NotImplementedError(
            f"interpret_roll_bonus({ability.name}): expected an effect list"
        )

    bonuses: list[int] = []
    for block in ability.effect:
        if block.get("verb") != "apply_modifier" or block.get("hook") != "flat":
            raise NotImplementedError(
                f"interpret_roll_bonus({ability.name}): only an apply_modifier "
                f"flat bonus is modeled (got verb={block.get('verb')!r}, "
                f"hook={block.get('hook')!r})"
            )
        if block.get("stat") != "attack_roll":
            raise NotImplementedError(
                f"interpret_roll_bonus({ability.name}): only an attack_roll bonus "
                f"is modeled (got stat={block.get('stat')!r})"
            )
        bonuses.append(block["value"])

    if len(bonuses) != 1:
        raise NotImplementedError(
            f"interpret_roll_bonus({ability.name}): expected exactly one flat "
            f"block, got {len(bonuses)}"
        )
    cost = ability.cost or {}
    resource = cost.get("resource") or {}
    return RollBonusSpec(
        bonus=bonuses[0],
        resource_type=resource.get("type"),
        count=resource.get("count", 1),
    )


# ---------------------------------------------------------------------------
# Effect interpreter — intercept_event (AC bump) → InterceptSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InterceptSpec:
    """The data-derived pieces of an `intercept_event` ability (Flourish Parry).

    The policy keeps ALL the decision logic — whether to react at all (only when
    the AC bump would flip the hit to a miss), the once-per-round reaction gate,
    and whether to attach a counter.  The interpreter only states WHAT the
    interception does.

    Fields
    ------
    ac_bonus:
        AC added against the intercepted attack (Flourish Parry = +CHA).
    """

    ac_bonus: int


def interpret_intercept(
    ability: Ability,
    context: dict[str, int] | None = None,
) -> InterceptSpec:
    """Translate an `intercept_event` AC-bump ability into an InterceptSpec.

    Models the one form the build needs: a single `intercept_event` whose
    `modification` is an `apply_modifier` flat AC bump.  The AC amount may be a
    literal (`value: 5`) or a runtime `amount: {ability_modifier: <stat>}`
    resolved against `context` (Flourish Parry = +CHA).  Anything else (a
    force-miss interception, a non-AC stat, multiple blocks) raises loudly.
    """
    if not isinstance(ability.effect, list):
        raise NotImplementedError(
            f"interpret_intercept({ability.name}): expected an effect list"
        )

    ac_bonuses: list[int] = []
    for block in ability.effect:
        verb = block.get("verb")
        if verb != "intercept_event":
            raise NotImplementedError(
                f"interpret_intercept({ability.name}): verb {verb!r} is not an "
                f"intercept_event"
            )
        if block.get("modification") != "apply_modifier":
            raise NotImplementedError(
                f"interpret_intercept({ability.name}): only an apply_modifier "
                f"interception is modeled (got {block.get('modification')!r})"
            )
        if block.get("hook") != "flat" or block.get("stat") != "ac":
            raise NotImplementedError(
                f"interpret_intercept({ability.name}): only a flat AC bump is "
                f"modeled (hook={block.get('hook')!r}, stat={block.get('stat')!r})"
            )
        if "value" in block:
            ac_bonuses.append(block["value"])
        else:
            ac_bonuses.append(_resolve_amount(block, context, ability.name))

    if len(ac_bonuses) != 1:
        raise NotImplementedError(
            f"interpret_intercept({ability.name}): expected exactly one "
            f"intercept_event block, got {len(ac_bonuses)}"
        )
    return InterceptSpec(ac_bonus=ac_bonuses[0])


# ---------------------------------------------------------------------------
# Dice scaling — the schema's `dice: {base, increment, every_n_levels,
# level_reference}` form → a concrete (count, sides), given the level it scales on
# ---------------------------------------------------------------------------

# The character levels at which a 2024 cantrip gains an extra damage die (the
# canonical 5.5e rule: 1 die, +1 at 5 / 11 / 17).  Named here rather than buried
# in a formula so the rule is legible and a future variant can override it.
_CANTRIP_THRESHOLDS: tuple[int, ...] = (5, 11, 17)


def _level_from_context(
    level_reference: str | None,
    context: dict[str, int] | None,
    ability_name: str,
) -> int:
    """Resolve the level value a `level_reference` names against `context`.

    The schema's dice block scales on an abstract level (`character_level`,
    `slot_level`, …); the policy supplies the concrete value at fire-time via
    `context` (e.g. {"character_level": 5}).  Mirrors `_resolve_amount`: data +
    context in → int out, no policy state leaking in.
    """
    if level_reference is None:
        raise NotImplementedError(
            f"{ability_name}: scaling dice need a `level_reference` "
            f"(e.g. character_level, slot_level)"
        )
    if context is None or level_reference not in context:
        raise ValueError(
            f"{ability_name}: no value for level_reference {level_reference!r} "
            f"in context {context!r}"
        )
    return context[level_reference]


def _resolve_scaling_dice(
    spec: "str | dict",
    context: dict[str, int] | None = None,
    ability_name: str = "?",
) -> tuple[int, int]:
    """Translate one `dice` spec into a concrete (count, sides) at the given level.

    The shared seam for every dice-scaling form (CLAUDE.md #1 — D&D scaling rules
    live in DATA, the engine just folds them).  Three shapes:

      - **literal** — ``"1d8"`` or ``{base: "1d8"}`` with no scaling keys →
        (1, 8), level-independent.  (Wrathful Smite, every fixed rider.)
      - **cantrip** — ``{base: "1d8", scaling: cantrip,
        level_reference: character_level}`` → the canonical 5.5e cantrip rule:
        +1 die at character level 5 / 11 / 17 (Sacred Flame 1d8→2d8→3d8→4d8).
        The thresholds are NON-uniform from level 1, so this is its own named
        mode rather than the uniform `every_n_levels` form below.
      - **uniform** (``increment`` / ``every_n_levels``) — +N dice per
        ``every_n_levels`` of the referenced level (Divine Smite / Searing Arc
        Strike upcast: +1d8 per slot level).  **Deferred to primitive #3** — it
        raises here so the gap surfaces loudly rather than silently dropping
        upcast dice.

    Returns a single (count, sides); the die SIZE never changes, only the count.
    """
    if isinstance(spec, str):
        return parse_dice(spec)

    base_count, sides = parse_dice(spec["base"])
    scaling = spec.get("scaling")
    level_reference = spec.get("level_reference")

    if scaling == "cantrip":
        if level_reference != "character_level":
            raise NotImplementedError(
                f"{ability_name}: cantrip scaling is by character_level "
                f"(got level_reference={level_reference!r})"
            )
        level = _level_from_context(level_reference, context, ability_name)
        steps = sum(1 for t in _CANTRIP_THRESHOLDS if level >= t)
        return base_count + steps, sides

    if "increment" in spec or "every_n_levels" in spec:
        raise NotImplementedError(
            f"{ability_name}: uniform `increment`/`every_n_levels` scaling is "
            f"primitive #3 (upcast) — not modeled yet"
        )

    # A `{base: ...}` block with no scaling keys is just a literal.
    return base_count, sides


def interpret_hit_rider(ability: Ability) -> HitRiderSpec:
    """Translate an on-hit `damage` rider ability into a HitRiderSpec.

    Reads the `damage` verb's dice (literal form only for now, via
    `_resolve_scaling_dice`) and the cost block's action economy + resource type.
    Uniform `increment`/upcast scaling is not yet modeled — the shared dice helper
    raises so the gap surfaces loudly rather than silently dropping upcast dice.
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
        dice.append(_resolve_scaling_dice(block.get("dice"), ability_name=ability.name))

    cost = ability.cost or {}
    resource = cost.get("resource") or {}
    return HitRiderSpec(
        extra_damage_dice=dice,
        action_cost=cost.get("action_economy"),
        resource_type=resource.get("type"),
        min_level=resource.get("min_level"),
    )


# ---------------------------------------------------------------------------
# Effect interpreter — save-FOR-damage spell → SaveSpellSpec
# ---------------------------------------------------------------------------

# The schema's `save` verb names an ABILITY (dexterity, …); the engine rolls a
# concrete save stat (`dex_save`, …).  This maps the schema vocabulary onto the
# stat keys resolve_saving_throw reads.
ABILITY_SAVE_MAP: dict[str, str] = {
    "strength": "str_save",
    "dexterity": "dex_save",
    "constitution": "con_save",
    "intelligence": "int_save",
    "wisdom": "wis_save",
    "charisma": "cha_save",
}


@dataclass(frozen=True)
class SaveSpellSpec:
    """The data-derived pieces of a save-FOR-damage spell (Sacred Flame, Burning
    Hands) — the fields the policy turns into a `Choice(action_type="save_spell")`
    / `SaveDamageEvent`.

    The interpreter states only WHAT the spell does at this character level — which
    save the target rolls, against which DC stat, the (already scaled) damage dice,
    and how a made save is handled.  WHEN/whether to cast and which resource it
    spends stay in the policy.

    Fields
    ------
    save_stat:
        The TARGET's saving-throw stat, e.g. "dex_save" (Sacred Flame).
    dc_stat:
        The CASTER's DC stat the save is rolled against, e.g. "spell_save_dc".
    damage_dice:
        The (count, sides) for this cast, already resolved for the supplied
        character level via `_resolve_scaling_dice` (Sacred Flame 1d8→4d8).
    on_save:
        "none" (save negates — Sacred Flame) or "half" (save-for-half — Burning
        Hands).  Defaults to "none".
    damage_bonus:
        Flat damage added to the spell's dice (0 for these cantrips).
    """

    save_stat: str
    dc_stat: str
    damage_dice: tuple[int, int]
    on_save: str = "none"
    damage_bonus: int = 0


def interpret_save_spell(
    ability: Ability,
    context: dict[str, int] | None = None,
) -> SaveSpellSpec:
    """Translate a save-FOR-damage spell (`save` + `damage` effect blocks) into a
    SaveSpellSpec, resolving scaled dice against `context` (e.g. the char level).

    The schema's canonical save-for-damage shape (core_examples #4, divine-save
    cantrips) is two effect blocks: a ``verb: save`` (which ability, vs which DC)
    followed by a ``verb: damage`` (dice + on_save).  Sacred Flame's damage dice
    carry ``scaling: cantrip`` → the dice grow with character level via
    `_resolve_scaling_dice`; pass the level in ``context``
    (e.g. {"character_level": 5}).

    Raises loudly on anything outside this single-save / single-damage shape so
    the schema/engine gap surfaces rather than being silently dropped.
    """
    if not isinstance(ability.effect, list):
        raise NotImplementedError(
            f"interpret_save_spell({ability.name}): expected an effect list "
            f"(choose_one not supported here)"
        )

    save_block: dict | None = None
    damage_block: dict | None = None
    for block in ability.effect:
        verb = block.get("verb")
        if verb == "save":
            if save_block is not None:
                raise NotImplementedError(
                    f"interpret_save_spell({ability.name}): more than one `save` "
                    f"block is not modeled"
                )
            save_block = block
        elif verb == "damage":
            if damage_block is not None:
                raise NotImplementedError(
                    f"interpret_save_spell({ability.name}): more than one `damage` "
                    f"block is not modeled"
                )
            damage_block = block
        else:
            raise NotImplementedError(
                f"interpret_save_spell({ability.name}): verb {verb!r} not "
                f"supported (expected `save` + `damage`)"
            )

    if save_block is None or damage_block is None:
        raise NotImplementedError(
            f"interpret_save_spell({ability.name}): expected both a `save` and a "
            f"`damage` block (got save={save_block is not None}, "
            f"damage={damage_block is not None})"
        )

    ability_name = save_block.get("ability")
    if ability_name not in ABILITY_SAVE_MAP:
        raise NotImplementedError(
            f"interpret_save_spell({ability.name}): unknown save ability "
            f"{ability_name!r} (expected one of {sorted(ABILITY_SAVE_MAP)})"
        )
    save_stat = ABILITY_SAVE_MAP[ability_name]

    dc_stat = save_block.get("dc_reference")
    if not dc_stat:
        raise NotImplementedError(
            f"interpret_save_spell({ability.name}): `save` block needs a "
            f"`dc_reference` (e.g. spell_save_dc)"
        )

    damage_dice = _resolve_scaling_dice(
        damage_block.get("dice"), context, ability.name
    )
    on_save = damage_block.get("on_save", "none")
    if on_save not in ("none", "half"):
        raise NotImplementedError(
            f"interpret_save_spell({ability.name}): on_save {on_save!r} not "
            f"modeled (expected 'none' or 'half')"
        )

    return SaveSpellSpec(
        save_stat=save_stat,
        dc_stat=dc_stat,
        damage_dice=damage_dice,
        on_save=on_save,
    )
