"""
build_adapters.py — adapters for the three builds that exist today.

Each adapter WRAPS its build's existing factory unchanged (evaluation_framework.md
§2: "adapt, do not rewrite" — those factories back validated DPR baselines) and
adds the two things the evaluation layer needs and the factories do not provide:

* a **role-tagged roster** instead of a positional tuple (§3.3), so nothing
  downstream ever has to know that Silvertail's factory returns the beast third;
* a **``describe()``** block of RESOLVED parameters for §4 provenance.

Registration happens at import time; ``adapters._ensure_builtin_adapters`` pulls
this module in on the first registry lookup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..builds import silvertail, starfire_scion, war_angel
from .adapters import OptionSpec, register
from .roster import Roster

if TYPE_CHECKING:                                    # pragma: no cover
    from ..day_runner import DayRunner
    from ..entity import Entity
    from ..rng import SeededRNG
    from .config import RunConfig


def _resolved_options(adapter, config: "RunConfig") -> dict[str, Any]:
    """Every declared axis with the value ACTUALLY used — the caller's where given,
    the schema default otherwise.

    §4's load-bearing distinction: an unset option must be reported as the value
    that was used, never as the word "default".
    """
    return {
        name: config.build_options.get(name, spec.default)
        for name, spec in adapter.option_schema().items()
    }


def _extra_entities(runner: "DayRunner", known: "list[Entity]") -> list["Entity"]:
    """Entities the runner holds that the factory did not hand back.

    Some factories append an entity to the roster internally (Starfire Scion's
    passive party member under ``with_party``) without returning it.  Recovering
    them by SET DIFFERENCE — not by index — keeps the adapter free of the
    tuple-position coupling this whole layer exists to remove.
    """
    known_ids = {e.id for e in known}
    return [e for e in runner.entities if e.id not in known_ids]


# ---------------------------------------------------------------------------
# War Angel — no scenario axes, contiguous levels 1–16
# ---------------------------------------------------------------------------

class WarAngelAdapter:
    """Paladin/Fighter/Bard "War Angel" — the build ``src/validation.py`` measures.

    Reproducing that harness's numbers exactly through this adapter is the
    correctness proof for the whole evaluation layer (§12).
    """

    name = "war_angel"

    def available_levels(self) -> list[int]:
        return sorted(war_angel.LEVELS)

    def option_schema(self) -> dict[str, OptionSpec]:
        return {}                    # no scenario axes (§2's survey)

    def build(self, config: "RunConfig", rng: "SeededRNG"):
        runner, char, dummy = war_angel.make_day_runner(
            config.level, rng, config.rounds_per_combat,
        )
        return runner, Roster(characters=[char], enemies=[dummy])

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        row = war_angel.LEVELS[config.level]
        enemy_attack = row.get("enemy_attack")
        return {
            "build": self.name,
            "level": config.level,
            "options": {},
            # Structural facts the factory decides off the level's data row.
            "enemy_policy": "scripted" if enemy_attack else None,
            "enemy_n_attacks": enemy_attack["n_attacks"] if enemy_attack else 0,
            "enemy_char_target_prob": (
                enemy_attack["char_target_prob"] if enemy_attack else 0.0
            ),
            "daily_plan": config.level >= 5,     # Magic Weapon / Prayer of Healing hooks
        }


# ---------------------------------------------------------------------------
# Starfire Scion — five scenario axes, sparse levels
# ---------------------------------------------------------------------------

class StarfireScionAdapter:
    """Druid/Monk "Starfire Scion" — the widest scenario surface of the three."""

    name = "starfire_scion"

    def available_levels(self) -> list[int]:
        return sorted(starfire_scion.LEVELS)

    def option_schema(self) -> dict[str, OptionSpec]:
        return {
            "primal_strike_unarmed": OptionSpec(
                "primal_strike_unarmed", default=None, values=(None, True, False),
                description=(
                    "L15+ Primal Strike rider gating. None = the level row's RAW "
                    "default (weapon attacks only); True also rides unarmed strikes "
                    "(the non-RAW comparison)."
                ),
            ),
            "fourth_level_spell": OptionSpec(
                "fourth_level_spell", default="fount_of_moonlight",
                values=("fount_of_moonlight", "fire_shield"),
                description="L15+ which 4th-level spell the single slot prepares.",
            ),
            "precast_mode": OptionSpec(
                "precast_mode", default=None, values=(None, "always", "never", "rng"),
                description=(
                    "Whether the 4th-level buff is pre-cast (free) or cast in combat. "
                    "None = each effect's legacy default and draws no dice."
                ),
            ),
            "precast_prob": OptionSpec(
                "precast_prob", default=0.5, values=None,
                description="Pre-cast probability when precast_mode='rng'.",
            ),
            "with_party": OptionSpec(
                "with_party", default=False, values=(True, False),
                description=(
                    "L15+ register a passive party member and split the enemy's "
                    "swings across {character, party}."
                ),
            ),
        }

    def build(self, config: "RunConfig", rng: "SeededRNG"):
        opts = _resolved_options(self, config)
        runner, char, dummy = starfire_scion.make_day_runner(
            config.level, rng, config.rounds_per_combat, **opts,
        )
        # The passive party member is appended to the runner's roster internally
        # and never returned — recover it by difference, not by position.
        allies = _extra_entities(runner, [char, dummy])
        return runner, Roster(characters=[char], allies=allies, enemies=[dummy])

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        opts = _resolved_options(self, config)
        row = starfire_scion.LEVELS[config.level]
        enemy_attack = row.get("enemy_attack")

        # Genuine §4 resolution: primal_strike_unarmed=None is not "default", it is
        # whatever the level row's raw_unarmed flag says (and is meaningless at a
        # level with no Primal Strike at all).
        ps = row.get("primal_strike")
        if ps is None:
            resolved_ps = None
            ps_source = "level has no Primal Strike"
        elif opts["primal_strike_unarmed"] is None:
            resolved_ps = ps["raw_unarmed"]
            ps_source = f"starfire_scion.LEVELS[{config.level}]['primal_strike']['raw_unarmed']"
        else:
            resolved_ps = opts["primal_strike_unarmed"]
            ps_source = "config.build_options"

        return {
            "build": self.name,
            "level": config.level,
            "options": opts,
            "primal_strike_unarmed_effective": resolved_ps,
            "primal_strike_unarmed_source": ps_source,
            "enemy_policy": "scripted" if enemy_attack else None,
            "enemy_targeting": (
                "weighted_roster" if (enemy_attack and opts["with_party"])
                else "single_target" if enemy_attack else None
            ),
        }


# ---------------------------------------------------------------------------
# Silvertail — the summon build; four axes, three levels
# ---------------------------------------------------------------------------

class SilvertailAdapter:
    """Druid "Silvertail" with a primal companion.

    The build that proves the roster abstraction earns its keep: its factory
    returns FOUR values with the summon in the middle, so any position-based
    reader breaks on it.  Here the beast is tagged ``summons`` and therefore lands
    in :attr:`Roster.party_source_ids` but never in
    :attr:`Roster.headline_source_ids` — the §3.3 rule that the headline column is
    the character's own and a summon column sits BESIDE it, never merged.
    """

    name = "silvertail"

    def available_levels(self) -> list[int]:
        return sorted(silvertail.LEVELS)

    def option_schema(self) -> dict[str, OptionSpec]:
        return {
            "beast_effect": OptionSpec(
                "beast_effect", default=None,
                values=(None, "warding_bond", "protection", "bless", "aid"),
                description="The 7c-on-summon effect installed ON the companion.",
            ),
            "mortal_beast": OptionSpec(
                "mortal_beast", default=False, values=(True, False),
                description=(
                    "True = the companion winks out at 0 HP (summon survival); "
                    "False = the threshold-immortal beast effects are isolated against."
                ),
            ),
            "recast": OptionSpec(
                "recast", default=False, values=(True, False),
                description="Between-combats hook that revives a dead companion.",
            ),
            "zone_effect": OptionSpec(
                "zone_effect", default=None, values=(None, "spirit_guardians"),
                description="The 7b zone/emanation the master opens combat with.",
            ),
        }

    def build(self, config: "RunConfig", rng: "SeededRNG"):
        opts = _resolved_options(self, config)
        runner, char, beast, dummy = silvertail.make_silvertail_runner(
            config.level, rng, config.rounds_per_combat, **opts,
        )
        return runner, Roster(characters=[char], summons=[beast], enemies=[dummy])

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        opts = _resolved_options(self, config)
        row = silvertail.LEVELS[config.level]
        enemy_attack = row.get("enemy_attack")
        return {
            "build": self.name,
            "level": config.level,
            "options": opts,
            "enemy_policy": "baseline" if enemy_attack else None,
            # The factory picks the focus target off zone_effect: with a zone the
            # enemy tanks the master (so its hits can break concentration),
            # otherwise it focus-fires the beast.
            "enemy_focus": (
                None if not enemy_attack
                else "character" if opts["zone_effect"] is not None
                else "summon"
            ),
            "enemy_damage_type": enemy_attack.get("damage_type") if enemy_attack else None,
        }


WAR_ANGEL = register(WarAngelAdapter())
STARFIRE_SCION = register(StarfireScionAdapter())
SILVERTAIL = register(SilvertailAdapter())
