"""
The BASELINE CHARACTER's declared progression (evaluation_framework.md §3.5.1).

The approved table is pinned here as an ASSERTION rather than left as a comment in
``character_stats``, for the reason s53 wrote down after §6.1 carried a wrong tally for
a session: **a tallied table in prose has nothing behind it.**  Every number the user
reviewed — the eight DECLARED columns and all six DERIVED check columns — is reproduced
below from ``src/builds/character_stats.py``'s rules, so a retune that breaks the
approved table fails here instead of printing new numbers under the old heading.

THE ROLL CALL (per-feature ritual step 5) — one row per DECLARATION this change
touches, one column naming the fixture that covers each VALUE.  Written before the
tests, which is the only time it finds anything.

| declaration | values | fixture covering each |
|---|---|---|
| the progression itself | 20 levels × 8 declared columns | ``test_progression_reproduces_the_approved_declared_table`` (all 20 rows, not a sample) |
| ``_primary_mod`` | +3 (L1-3) / +4 (L4-7) / +5 (L8-20) | same test — the ASI boundaries are rows 4 and 8 of it |
| ``_ac`` | 16 / 17 / 18 / 19 | same test — all four plateaus are in the 20 rows |
| ``_pb`` | +2 / +3 / +4 / +5 / +6 | same test |
| ``attacks`` | 1 (L<5) / 2 (L>=5) | same test |
| ``_hp`` rounding | the 10 levels landing on a half / the 10 landing whole | ``test_hp_rounding_is_half_to_even_and_that_is_what_the_table_needs`` covers the half case EXPLICITLY, because round-half-up would break 10 of 20 rows |
| ``_spell_slots`` | the published half-caster rows (L>=2) / the BORROWED L1 row | ``test_level_1_borrows_the_half_caster_level_2_row`` |
| ``_saves`` proficiency | proficient (primary, CON) / unproficient (DEX, WIS, INT, CHA) | ``test_two_saves_are_proficient_and_four_are_not`` |
| ``baseline_save`` key | a known key / an unknown key | ``test_an_unknown_save_key_raises_rather_than_reading_as_zero`` |
| ``_row`` level | in range / out of range | ``test_an_out_of_range_level_raises`` |
| §3.5.1 property 1 (two-way hit band) | outgoing in band / incoming NOT in band | ``test_outgoing_hit_rate_holds_the_60_70_band_at_every_level`` and ``test_incoming_hit_rate_rises_monotonically_and_leaves_the_band`` — see the note on that pair |
| §3.5.1 property 2 (conc pass falls) | — | ``test_concentration_pass_rate_falls_from_75_to_35_percent`` |
| §3.5.1 property 3 (CON save +7 at L13) | — | ``test_con_save_reaches_plus_7_at_l13_above_both_real_builds`` |
| ``make_baseline_character`` | — | ``test_the_constructor_carries_a_complete_stat_block`` |
| ``make_party_member`` | — | ``test_a_party_member_is_a_passive_pool_at_a_peers_ac`` |
| no new dice | — | ``test_neither_constructor_draws_a_die`` |

**THE EMPTY CELL THE ROLL CALL FOUND, and it is in §3.5.1's own prose.** Property 1 is
stated as "hit rates stay inside a 60-70% band in BOTH directions across all 20 levels".
Measured against the section's own approved table, the OUTGOING rate does exactly that at
all 20 levels; the INCOMING rate reads 50% at L1-2, 55% at L3-6, 60-70% only at L7-14,
then 75% at L15-18 and 80% at L19-20 — in band at 8 of 20 levels and out of it at 12.
The claim and its refutation are in the same section, which is the shape s52 found in
§6.1 ("never worse than independent seeding" against its own 0.95x row) and s53 found
twice more.  So the property is asserted here in the two halves that are TRUE and
measured: the outgoing band holds everywhere, and the incoming rate is monotone
non-decreasing from 50% to 80% — which is not a defect but the same deliberate mechanism
as property 2, since a rising incoming hit rate is what drives ``conc pass`` down.
"""

from __future__ import annotations

import pytest

from src.builds import character_stats as C
from src.builds import enemy_stats as E
from src.rng import SeededRNG


# ---------------------------------------------------------------------------
# §3.5.1's approved table, transcribed ONCE, as data
# ---------------------------------------------------------------------------
#
# Columns: lvl, pb, primary, ac, attack, spell_dc, con_save, attacks, hp
# then the six DERIVED check columns: enemy_ac, we_hit, enemy_to_hit, they_hit,
# conc_dc, conc_pass.  Rates are percentages, as the design table prints them.
APPROVED = [
    # lvl  pb pri  ac atk  dc con atk#  hp | eAC we% eTH th% cDC cp%
    (   1,  2,  3, 16,  5, 13,  4,  1,   10,  13, 65,  5, 50, 10, 75),
    (   2,  2,  3, 16,  5, 13,  4,  1,   16,  14, 60,  5, 50, 10, 75),
    (   3,  2,  3, 16,  5, 13,  4,  1,   23,  14, 60,  6, 55, 10, 75),
    (   4,  2,  4, 16,  6, 14,  4,  1,   30,  15, 60,  6, 55, 10, 75),
    (   5,  3,  4, 17,  7, 15,  5,  2,   36,  15, 65,  7, 55, 10, 80),
    (   6,  3,  4, 17,  7, 15,  5,  2,   42,  15, 65,  7, 55, 10, 80),
    (   7,  3,  4, 17,  7, 15,  5,  2,   49,  16, 60,  8, 60, 10, 80),
    (   8,  3,  5, 17,  8, 16,  5,  2,   56,  16, 65,  8, 60, 10, 80),
    (   9,  4,  5, 17,  9, 17,  6,  2,   62,  16, 70,  9, 65, 10, 85),
    (  10,  4,  5, 17,  9, 17,  6,  2,   68,  16, 70,  9, 65, 10, 85),
    (  11,  4,  5, 18,  9, 17,  6,  2,   75,  17, 65, 10, 65, 11, 80),
    (  12,  4,  5, 18,  9, 17,  6,  2,   82,  17, 65, 10, 65, 13, 70),
    (  13,  5,  5, 18, 10, 18,  7,  2,   88,  17, 70, 11, 70, 13, 75),
    (  14,  5,  5, 18, 10, 18,  7,  2,   94,  17, 70, 11, 70, 15, 65),
    (  15,  5,  5, 18, 10, 18,  7,  2,  101,  18, 65, 12, 75, 16, 60),
    (  16,  5,  5, 18, 10, 18,  7,  2,  108,  18, 65, 12, 75, 18, 50),
    (  17,  6,  5, 19, 11, 19,  8,  2,  114,  18, 70, 13, 75, 18, 55),
    (  18,  6,  5, 19, 11, 19,  8,  2,  120,  19, 65, 13, 75, 18, 55),
    (  19,  6,  5, 19, 11, 19,  8,  2,  127,  19, 65, 14, 80, 20, 45),
    (  20,  6,  5, 19, 11, 19,  8,  2,  134,  19, 65, 14, 80, 22, 35),
]


def _d20_success_pct(bonus: int, dc: int) -> int:
    """P(d20 + bonus >= dc) as a percentage, with the natural-1 / natural-20 bounds.

    The derived columns of §3.5.1's table are attack rolls and saving throws against a
    fixed DC, so this is the whole model behind all six of them.
    """
    need = dc - bonus
    if need <= 1:
        return 95
    if need > 20:
        return 5
    return (21 - need) * 5


def _conc_dc(level: int) -> int:
    """The concentration DC a hit from the standardized enemy forces at *level*:
    half the MEAN damage of one swing, floor, minimum 10 (the 2024 rule)."""
    n, sides, bonus = E.baseline_attack_dice(level)
    return max(10, int((n * (sides + 1) / 2 + bonus) // 2))


# ---------------------------------------------------------------------------
# The declared columns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("row", APPROVED, ids=[f"L{r[0]}" for r in APPROVED])
def test_progression_reproduces_the_approved_declared_table(row):
    """Every DECLARED column, at every one of the 20 levels.

    All 20 rows rather than a structural sample, because the thing being pinned is the
    table the user approved — and because the four ``_ac`` plateaus, the two ASI
    boundaries and the Extra Attack step are each only visible at particular levels.
    """
    lvl, pb, primary, ac, atk, dc, con, attacks, hp = row[:9]
    assert C.baseline_pb(lvl) == pb
    assert C.baseline_primary_mod(lvl) == primary
    assert C.baseline_ac(lvl) == ac
    assert C.baseline_attack_bonus(lvl) == atk
    assert C.baseline_spell_dc(lvl) == dc
    assert C.baseline_save(lvl, "con_save") == con
    assert C.baseline_attacks(lvl) == attacks
    assert C.baseline_hp(lvl) == hp


@pytest.mark.parametrize("row", APPROVED, ids=[f"L{r[0]}" for r in APPROVED])
def test_derived_columns_reproduce_the_approved_sanity_check(row):
    """The six DERIVED columns — the ones §3.5.1 says "are the sanity check, and are
    what the user reviewed".

    They are not inputs, so pinning them pins the RELATIONSHIP between this track and
    ``enemy_stats``: a change to either table that breaks the pairing fails here. That
    is the point of property 1, and it is why this is a separate test from the declared
    columns rather than more assertions in the same one.
    """
    lvl, enemy_ac, we_hit, enemy_to_hit, they_hit, conc_dc, conc_pass = (
        row[0], row[9], row[10], row[11], row[12], row[13], row[14])
    assert E.baseline_ac(lvl) == enemy_ac
    assert E.baseline_attack_bonus(lvl) == enemy_to_hit
    assert _d20_success_pct(C.baseline_attack_bonus(lvl), enemy_ac) == we_hit
    assert _d20_success_pct(enemy_to_hit, C.baseline_ac(lvl)) == they_hit
    assert _conc_dc(lvl) == conc_dc
    assert _d20_success_pct(C.baseline_save(lvl, "con_save"), conc_dc) == conc_pass


def test_hp_rounding_is_half_to_even_and_that_is_what_the_table_needs():
    """The HP rule is ``10 + 6.5*(level-1)``, and HALF of the levels land on a .5.

    Round-half-up would give 17 / 30 / 43 / 56 / 69 / 82 / 95 / 108 / 121 / 134 at the
    ten half-landing levels, against the approved 16 / 30 / 42 / 56 / 68 / 82 / 94 /
    108 / 120 / 134 — so it would break 6 of those 10 rows. The branch is real and the
    convenient instance (a whole-numbered level) does not exercise it.
    """
    halves = [lvl for lvl in C.LEVELS if (10 + 6.5 * (lvl - 1)) % 1 == 0.5]
    assert halves == [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]
    approved = {r[0]: r[8] for r in APPROVED}
    for lvl in halves:
        exact = 10 + 6.5 * (lvl - 1)
        assert C.baseline_hp(lvl) == approved[lvl]
        # Half-to-EVEN: the result is always the even neighbour of the exact value.
        assert C.baseline_hp(lvl) % 2 == 0
        assert abs(C.baseline_hp(lvl) - exact) == 0.5


def test_level_1_borrows_the_half_caster_level_2_row():
    """§3.5.1's capability set makes a concentration spell, a save-forcing spell and
    healing CORE at every level, and a half-caster has no slots at level 1.

    The deviation is deliberate and is the only place this table is not the published
    one: a core capability that is off at L1 makes L1 a different measurement from
    L2-20, which is the comparability defect §3.5 exists to remove.
    """
    assert C.baseline_spell_slots(1) == C.baseline_spell_slots(2) == (2,)
    # And above L1 the table IS the published half-caster progression, unshifted —
    # the borrow must not have slid every later row down one.
    assert C.baseline_spell_slots(5) == (4, 2)
    assert C.baseline_spell_slots(9) == (4, 3, 2)
    assert C.baseline_spell_slots(13) == (4, 3, 3, 1)
    assert C.baseline_spell_slots(17) == (4, 3, 3, 3, 1)
    assert C.baseline_spell_slots(20) == (4, 3, 3, 3, 2)


def test_two_saves_are_proficient_and_four_are_not():
    """§3.5.1: "the six saving throws with two proficient".

    Tests the BRANCH both ways: a proficient save carries PB and an unproficient one
    does not, which is only visible by watching what happens at a PB step.
    """
    for lvl in C.LEVELS:
        saves = C.baseline_saves(lvl)
        assert set(saves) == set(C.SAVE_KEYS)
        pb = C.baseline_pb(lvl)
        # proficient: primary + CON
        assert saves[C.PRIMARY_SAVE_KEY] == pb + C.baseline_primary_mod(lvl)
        assert saves["con_save"] == pb + C.CON_MOD
        # unproficient: the bare ability modifier, flat across all 20 levels
        assert saves["dex_save"] == 2
        assert saves["wis_save"] == 1
        assert saves["int_save"] == 0
        assert saves["cha_save"] == 0
    # The PB step at L5 moves both proficient saves and neither unproficient one.
    before, after = C.baseline_saves(4), C.baseline_saves(5)
    assert after["con_save"] - before["con_save"] == 1
    assert after["dex_save"] == before["dex_save"]


def test_an_unknown_save_key_raises_rather_than_reading_as_zero():
    """A missing ``base_stats`` key reading as a silent 0 is the defect §3.5 was
    written about (AC 0 in 20 of 27 pairs; War Angel's dummy resolving saves at +0).
    The accessor refuses rather than joining in."""
    with pytest.raises(KeyError):
        C.baseline_save(5, "luck_save")


def test_an_out_of_range_level_raises():
    with pytest.raises(KeyError):
        C.baseline_ac(21)
    with pytest.raises(KeyError):
        C.baseline_ac(0)


# ---------------------------------------------------------------------------
# §3.5.1's three properties — the thing a retune must preserve
# ---------------------------------------------------------------------------

def test_outgoing_hit_rate_holds_the_60_70_band_at_every_level():
    """Property 1, the half that is true: "the cheapest available check on the whole
    progression".

    If this fails after a retune, the character's attack track and ``enemy_stats``'
    AC track have drifted apart — which is exactly what the property is for.
    """
    rates = {lvl: _d20_success_pct(C.baseline_attack_bonus(lvl), E.baseline_ac(lvl))
             for lvl in C.LEVELS}
    out_of_band = {lvl: r for lvl, r in rates.items() if not 60 <= r <= 70}
    assert out_of_band == {}, f"outgoing hit rate left the 60-70% band at {out_of_band}"


def test_incoming_hit_rate_rises_monotonically_and_leaves_the_band():
    """Property 1's OTHER half, measured rather than quoted — and the measurement
    contradicts the sentence.

    §3.5.1 says the band holds "in BOTH directions across all 20 levels". The incoming
    rate is in band at 8 of 20 levels (L7-14) and out of it at 12: 50-55% below, 75-80%
    above. That is not a defect, and the assertion says what IS true instead: the rate
    is monotone non-decreasing and spans 50% to 80%. The rise is the same deliberate
    mechanism as property 2 — a character who gets hit more often fails more
    concentration checks — so the two properties are one fact stated twice, and the
    prose is what needs correcting, not the table.
    """
    rates = [_d20_success_pct(E.baseline_attack_bonus(lvl), C.baseline_ac(lvl))
             for lvl in C.LEVELS]
    assert rates == sorted(rates), "incoming hit rate should never fall with level"
    assert rates[0] == 50 and rates[-1] == 80
    in_band = [r for r in rates if 60 <= r <= 70]
    assert len(in_band) == 8, (
        "if this count changes, §3.5.1's property-1 sentence needs changing with it"
    )


def test_concentration_pass_rate_falls_except_at_the_four_pb_steps():
    """Property 2: concentration becomes a genuine cost at high level rather than a
    formality.

    **NOT monotone, and writing the claim as an assertion is what showed that.** The
    first cut of this test asserted a monotone fall, reasoning straight from §3.5.1's
    "falls 75% → 35%". The measured sequence rises at four levels — and they are
    EXACTLY the four PB steps (5, 9, 13, 17), because a PB step gives the character a
    whole +1 at once while the enemy's damage grows smoothly, so each one buys back a
    tier's worth of ground before the slide resumes. That is the mechanism, and it is a
    sharper property than monotonicity: it ties the shape of this curve to the one
    thing in the table that moves in steps. (Per the step-5 rule broadened in s50: when
    you can name a quantity's inputs and conclude it must move one way, that is exactly
    when to measure it.)
    """
    rates = {lvl: _d20_success_pct(C.baseline_save(lvl, "con_save"), _conc_dc(lvl))
             for lvl in C.LEVELS}
    assert rates[1] == 75 and rates[20] == 35
    pb_steps = {lvl for lvl in C.LEVELS
                if lvl > 1 and C.baseline_pb(lvl) > C.baseline_pb(lvl - 1)}
    assert pb_steps == {5, 9, 13, 17}
    rose = {lvl for lvl in C.LEVELS if lvl > 1 and rates[lvl] > rates[lvl - 1]}
    assert rose == pb_steps, (
        "the pass rate should rise only where the proficiency bonus does"
    )
    # And the overall direction is unambiguous either side of the midpoint.
    first_half = sum(rates[lvl] for lvl in range(1, 11)) / 10
    second_half = sum(rates[lvl] for lvl in range(11, 21)) / 10
    assert first_half == 79.0 and second_half == 59.0


def test_con_save_reaches_plus_7_at_l13_above_both_real_builds():
    """Property 3, and the reason it is written down: a reader comparing baseline
    concentration figures against the existing builds' is comparing a REPRESENTATIVE
    character against two sparse ones (War Angel +4, Starfire +2 at L13-15)."""
    assert C.baseline_save(13, "con_save") == 7


# ---------------------------------------------------------------------------
# The constructors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level", [1, 5, 10, 15, 20])
def test_the_constructor_carries_a_complete_stat_block(level):
    """Deliberately complete, not minimal — the AC-0 defect's direct cause was that
    ``Entity.stat()`` returns 0 for a missing key by design.

    Asserted through ``stat()`` rather than by inspecting ``base_stats``, because
    ``stat()`` is what the verbs actually read (CLAUDE.md's invariant) and a key
    present but misnamed would pass the weaker check.
    """
    char = C.make_baseline_character(level)
    assert char.hp == C.baseline_hp(level)
    assert char.stat("ac", (1, 0, 0)) == C.baseline_ac(level)
    assert char.stat("attack_bonus", (1, 0, 0)) == C.baseline_attack_bonus(level)
    assert char.stat("spell_save_dc", (1, 0, 0)) == C.baseline_spell_dc(level)
    assert char.stat("damage_dice", (1, 0, 0)) == C.WEAPON_DICE
    for key in C.SAVE_KEYS:
        assert char.stat(key, (1, 0, 0)) == C.baseline_save(level, key)
    # The slot ledger the §13 resource channel reads, and the Hit Dice the healing
    # channel's between-combat context needs a producer for.
    slots = C.baseline_spell_slots(level)
    for i, n in enumerate(slots):
        assert char.resources.maximum(f"spell_slot_{i + 1}") == n
    assert char.resources.maximum("hit_dice") == level


@pytest.mark.parametrize("level", [1, 10, 20])
def test_a_party_member_is_a_passive_pool_at_a_peers_ac(level):
    """§3.5.2: party members are PASSIVE HP pools — they absorb their share of the
    incoming attacks and do nothing else.

    The AC comes from THIS module, which is the whole reason the function exists:
    ``starfire_scion.make_party_member`` reads that build's own ``char_ac``, and a
    framework-standard party taking its AC from one particular character's level row
    is §3.4's coupling with the labels swapped.
    """
    member = C.make_party_member(level)
    assert member.stat("ac", (1, 0, 0)) == C.baseline_ac(level)
    for key in C.SAVE_KEYS:
        assert member.stat(key, (1, 0, 0)) == C.baseline_save(level, key)
    # Passive: no attack profile and no resources, so it can never deal damage.
    assert member.stat("attack_bonus", (1, 0, 0)) == 0
    assert member.resources.as_dict() == {}
    # An HP pool that cannot run out — see PARTY_MEMBER_HP.
    assert member.hp == C.PARTY_MEMBER_HP


def test_each_party_member_is_a_distinct_entity_with_its_own_name():
    """Three members in a party of four, and the roster rejects duplicate ids."""
    members = [C.make_party_member(10, i) for i in (1, 2, 3)]
    assert len({m.id for m in members}) == 3
    assert len({m.name for m in members}) == 3


def test_neither_constructor_draws_a_die():
    """Per-feature ritual step 3: a stray draw outside combat shifts the shared stream
    and breaks every ``GOLDEN_DPR`` point at once.

    Checked by COUNTING draws on a real ``SeededRNG`` rather than by reading the code,
    because the constructors reach into ``healing`` and ``resources`` and the claim is
    about everything they transitively call.
    """
    class CountingRNG(SeededRNG):
        calls = 0

        def roll(self, n, sides):
            CountingRNG.calls += 1
            return super().roll(n, sides)

    rng = CountingRNG(7)
    for level in C.LEVELS:
        C.make_baseline_character(level)
        C.make_party_member(level)
    assert CountingRNG.calls == 0
    # The probe itself works, so a zero above is a measurement and not a broken test.
    rng.roll_one(20)
    assert CountingRNG.calls == 1
