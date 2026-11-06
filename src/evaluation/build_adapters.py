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

THE ENEMY SEAM (s50, §3.4; completed s52)
-----------------------------------------
``build()`` returns ``(runner, roster)`` and does NOT install the enemy.  In s50 each of
the three adapters ended with its own unconditional ``enemy.install`` call, which was
safe while the default was ``build_default``; s52 moved the call into ``runner.simulate``,
because with ``enemy`` required an adapter that FORGOT it would face its factory's enemy
while provenance claimed the declared kind.  A call that must always happen belongs in
the one function every run goes through, not in three that each have to remember it —
which also means a new adapter cannot get this wrong.  The factories return a PASSIVE
enemy for the seam to install onto.

**``describe()`` no longer reports any enemy fact, and that deletion is the point.**
Through s50-s51 each block carried the facts its FACTORY decided (``enemy_policy``,
``enemy_n_attacks``, ``enemy_focus``, ``enemy_damage_type``, …), which was right while
those facts WERE the run's enemy under ``build_default`` and were the overwritten path
otherwise.  With the baked-in path gone, nothing read them: ``enemy.resolve``'s only
consumer of ``described`` was its ``build_default`` branch.  Keeping them would have
left plausible-looking enemy numbers in provenance with no consumer and no claim to
truth — the trap §7.6 was written about — so they are gone.  The authoritative enemy
block is ``enemy.resolve``, assembled from the config alone, because the enemy is not a
property of the build.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..builds import baseline_character, silvertail, starfire_scion, war_angel
from . import enemy as enemy_seam
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

    Some factories append an entity to the roster internally (Starfire Scion's old
    passive party member under the retired ``with_party`` axis) without returning it.
    Recovering them by SET DIFFERENCE — not by index — keeps the adapter free of the
    tuple-position coupling this whole layer exists to remove.  No shipped factory does
    this since s54; the helper stays because dropping an entity a factory made is
    exactly the failure it prevents.
    """
    known_ids = {e.id for e in known}
    return [e for e in runner.entities if e.id not in known_ids]


# ---------------------------------------------------------------------------
# War Angel — no scenario axes, contiguous levels 1–16
# ---------------------------------------------------------------------------

class WarAngelAdapter:
    """Paladin/Fighter/Bard "War Angel" — the build ``src/validation.py`` measured.

    Reproducing that harness's numbers exactly through this adapter WAS the correctness
    proof for the whole evaluation layer, from s43 to s51.  s52 deleted the harness, and
    §12 records why the swap is asymmetric: the goldens that replace it are a stronger
    PHYSICS signal and a weaker LAYER one, the layer half surviving in
    ``test_headline_column_is_the_characters_own_output``.
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
        roster = Roster(characters=[char], enemies=[dummy])
        return runner, roster

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        return {
            "build": self.name,
            "level": config.level,
            "options": {},
            "daily_plan": config.level >= 5,     # Magic Weapon / Prayer of Healing hooks
        }

    def forced_save_abilities(self, config: "RunConfig") -> "frozenset[str]":
        """NONE, at every level — and this is the declaration that makes step 8b fire.

        Verified rather than assumed: `src/builds/war_angel.py` contains no
        `save_stat`, no `action_type="save_spell"` and no zone, so nothing in its
        plan can put a save into the §13 channel in either direction.  Every save
        this build's rows record was forced BY the enemy ON the character.

        That is why its `saves_forced_per_round[cha_save|*]` read `0 +/- 0`,
        `converged=True`, `available=True` at ten of sixteen levels (§14): the
        enemy cannot force a CHA save below L11 and neither can the build, so the
        cell had no producer at all and still rendered as the most trustworthy row
        in its breakdown.
        """
        return frozenset()


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
        }

    def build(self, config: "RunConfig", rng: "SeededRNG"):
        opts = _resolved_options(self, config)
        runner, char, dummy = starfire_scion.make_day_runner(
            config.level, rng, config.rounds_per_combat, **opts,
        )
        # `_extra_entities` recovers anything the factory appended to the runner and
        # did not hand back, BY SET DIFFERENCE rather than by index. With `with_party`
        # retired (s54) this build appends nothing, so the list is empty today — the
        # call stays because the alternative is an adapter that silently drops an
        # entity the factory made, and that is the tuple-position coupling this whole
        # layer exists to remove. The framework's own party arrives later, from
        # `party.install`, and is not this adapter's business.
        allies = _extra_entities(runner, [char, dummy])
        roster = Roster(characters=[char], allies=allies, enemies=[dummy])
        return runner, roster

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        opts = _resolved_options(self, config)
        row = starfire_scion.LEVELS[config.level]

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
        }

    def forced_save_abilities(self, config: "RunConfig") -> "frozenset[str]":
        """``dex_save`` — Sacred Flame and Searing Arc Strike, both `save_spell`.

        Declared level-independently and that is DELIBERATE, per the protocol's
        over-inclusive rule: Sacred Flame is gated on a `spellfire_spark` and
        Searing Arc on focus points, so which levels can actually produce one is a
        function of resource state within a day rather than of the level row.
        Over-declaring leaves the cell available, which is the pre-8b behaviour and
        costs nothing; under-declaring would discard a real measurement.

        **`wis_save` is deliberately absent**, and it is the case the protocol's
        last paragraph is about.  `starfire_scion.py:830` rolls a `wis_save` for
        Sanctuary's `negate_save`, but that save is resolved in
        `resolve_attack_roll` and NOTHING records it — the channel has two writers
        and this is not one of them.  Declaring it would hold an empty cell open on
        the strength of a save no metric can see.
        """
        return frozenset({"dex_save"})


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
        roster = Roster(characters=[char], summons=[beast], enemies=[dummy])
        return runner, roster

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        opts = _resolved_options(self, config)
        return {
            "build": self.name,
            "level": config.level,
            "options": opts,
        }

    def forced_save_abilities(self, config: "RunConfig") -> "frozenset[str]":
        """``wis_save`` only when the Spirit Guardians zone is installed.

        The one adapter whose answer depends on an OPTION rather than on the build
        alone, which is why the protocol takes the whole `RunConfig`: a damaging
        zone fires a `SaveDamageEvent` at every occupant's turn boundary
        (`scheduler._fire_zone_saves`), so with `zone_effect='spirit_guardians'`
        the build is a producer in the damage channel and without it there is no
        zone to fire.  Read through `_resolved_options` so the default is the value
        actually used rather than whatever the caller omitted (§4).
        """
        opts = _resolved_options(self, config)
        if opts.get("zone_effect") != "spirit_guardians":
            return frozenset()
        # Read the ability off the SAME level-row entry the factory builds the zone
        # from, rather than repeating "wis_save" here: one source, so re-keying the
        # spell cannot leave the predicate answering about the old ability. A level
        # with no entry declares nothing, which matches the factory's own
        # `data.get("spirit_guardians")`.
        spec = silvertail.LEVELS[config.level].get("spirit_guardians")
        return frozenset() if spec is None else frozenset({spec["save_stat"]})


# ---------------------------------------------------------------------------
# The BASELINE CHARACTER — the framework's own declared subject (§3.5)
# ---------------------------------------------------------------------------

class BaselineCharacterAdapter:
    """The framework's declared SUBJECT (evaluation_framework.md §3.5), adapted.

    **Not a build**, and that is the point.  The other three adapters wrap character
    builds whose data is sparse exactly where the framework needs it complete, which
    is what makes a framework defect and a content gap indistinguishable.  This one
    wraps a subject that is complete at every level by construction, so a mechanism
    test can assert framework behaviour and mean it.

    All 20 levels, so it is also the only adapter whose ``available_levels`` is a
    full range rather than a sparse set — §3.2's note that level sets are sparse is
    about BUILDS, and this is the reason the framework never assumed otherwise.

    It is the one adapter that needs the roster AFTER the party is installed: the
    ``ally_buff`` axis has to land on a real ally, and the only honest source for one
    is ``RunConfig.party_size`` (§3.5.2).  ``runner.assemble`` therefore calls
    :meth:`bind_roster` between the party and the enemy, which is a seam the other
    three do not use and which is declared rather than inferred from whether an
    adapter happens to define the method.
    """

    name = "baseline"
    #: §3.5.2's seam: this adapter reads the installed party.  Declared as a
    #: capability rather than detected by ``hasattr``, so an adapter that forgets to
    #: implement ``bind_roster`` while setting this fails loudly.
    needs_roster = True

    def available_levels(self) -> list[int]:
        return list(baseline_character.cs.LEVELS)

    def option_schema(self) -> dict[str, OptionSpec]:
        return {
            "aoo_per_combat": OptionSpec(
                "aoo_per_combat", default=1, values=None,
                description=(
                    "Opportunity attacks the subject takes per combat, on rounds "
                    "pre-rolled at on_combat_start. DECLARED rather than constant "
                    "because THERE IS NO SPATIAL MODEL: 'the enemy moves out of "
                    "reach' is a FREQUENCY, not an event, and §4 records the "
                    "assumption instead of burying it (§3.5.1). Default 1, War "
                    "Angel's convention — its guide reached it by collapsing five "
                    "AoO timing slots into one. 0 draws no dice at all, so it is a "
                    "different stream and not merely a different count."
                ),
            ),
            "summon": OptionSpec(
                "summon", default=False, values=(True, False),
                description=(
                    "§3.5.1 axis: command a summon, so the per-summon damage column "
                    "and the roster-scoping checks have a producer. Deliberately a "
                    "WEAK attacker, so 'did this metric pool the character and the "
                    "summon?' stays detectable."
                ),
            ),
            "ally_buff": OptionSpec(
                "ally_buff", default=False, values=(True, False),
                description=(
                    "§3.5.1 axis: install a buff ON an ally, exercising the 'allies' "
                    "role as a buff TARGET rather than only as a damage sink. Needs "
                    "party_size > 1 — with no allies in the roster the axis does not "
                    "fire, because a policy inventing its own ally would be a second "
                    "source for the party (§3.5.2)."
                ),
            ),
            "reaction_mitigation": OptionSpec(
                "reaction_mitigation", default=False, values=(True, False),
                description=(
                    "§3.5.1 axis: a Shield-like reaction that raises AC against one "
                    "incoming hit, exercising the DEFENDER-side on_incoming_hit seam "
                    "and the character side of §5's mult(t). With the opportunity "
                    "attack also on, the subject double-books its reaction exactly "
                    "as War Angel L14+ does, and reactions_per_round is where that "
                    "shows (§8.2a) — reproduced rather than quietly fixed."
                ),
            ),
        }

    def build(self, config: "RunConfig", rng: "SeededRNG"):
        opts = _resolved_options(self, config)
        runner, char, dummy, beast = baseline_character.make_day_runner(
            config.level, rng, config.rounds_per_combat, **opts,
        )
        # The summon is tagged `summons`, so §3.3's rule applies to it unchanged: it
        # lands in `party_source_ids` and NEVER in `headline_source_ids`, and the
        # per-summon damage column falls out of the per-(source, target) ledger.
        roster = Roster(characters=[char],
                        summons=[beast] if beast is not None else [],
                        enemies=[dummy])
        return runner, roster

    def bind_roster(self, runner: "DayRunner", roster: "Roster",
                    config: "RunConfig") -> None:
        """Hand the policy the installed roster's allies (§3.5.2).

        Called by ``runner.assemble`` AFTER ``party.install`` and BEFORE
        ``enemy.install``.  It mutates no entity and draws no dice — it tells the
        policy which friendlies exist so the ``ally_buff`` axis can target one that
        the FRAMEWORK declared, instead of one the policy invented.
        """
        policy = runner.policies.get(roster.character.id)
        if policy is not None:
            policy._allies = list(roster.allies)         # noqa: SLF001 — the seam

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        opts = _resolved_options(self, config)
        row = baseline_character.cs.level_table()[config.level]
        return {
            "build": self.name,
            "level": config.level,
            "options": opts,
            "subject": "the framework's declared baseline character (§3.5.1)",
            # The resolved STAT BLOCK, named from the progression rather than from a
            # hand-authored row — the whole reason this subject exists.
            "progression": {
                "pb": row["pb"], "primary": row["primary"], "ac": row["ac"],
                "attack_bonus": row["attack_bonus"],
                "spell_save_dc": row["spell_save_dc"],
                "attacks": row["attacks"], "hp": row["hp"],
                "saves": dict(row["saves"]),
                "spell_slots": list(row["spell_slots"]),
            },
            "progression_source": (
                f"builds/character_stats — the §3.5.1 progression at level "
                f"{config.level}, derived from declared rules rather than authored "
                "per level"
            ),
        }

    def forced_save_abilities(self, config: "RunConfig") -> "frozenset[str]":
        """``baseline_character.SAVE_SPELL_SAVE`` — the subject's save-for-half spell.

        Read from the module constant rather than written out, so the subject's one
        save-forcing capability has a single source: §3.5.1 declares the save spell
        as a CORE capability present at every level (L1 borrows L2's slot row for
        exactly this reason), so the answer is level-independent and that is a
        property of the approved progression rather than a simplification.

        This is also the arm that proves the predicate does not over-reach: the
        subject forces `dex_save`, the band's enemy forces `dex_save`, and both at
        every level — so `[dex_save|*]` must stay available at L17-20 while
        `[int_save|*]`, which NEITHER side can produce there, goes unavailable.
        """
        return frozenset({baseline_character.SAVE_SPELL_SAVE})


WAR_ANGEL = register(WarAngelAdapter())
STARFIRE_SCION = register(StarfireScionAdapter())
SILVERTAIL = register(SilvertailAdapter())
BASELINE = register(BaselineCharacterAdapter())
