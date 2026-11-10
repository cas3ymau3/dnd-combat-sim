"""
test_eval_sweep.py — framework step 8c: the sweep declaration, manifest, CLI and cache
(``evaluation_framework.md`` §10, §10.1, §10.2).

Validation framing (§12, memory ``validate-mechanism-not-build-value``): nothing here
asserts a DPR.  Every test asserts a property of the sweep MECHANISM — which cells a
declaration resolves to, what the manifest says about them, when a cached record may be
served, and when the layer REFUSES rather than guesses.  A sweep is machinery for taking
measurements; its tests are about the machinery.

THE ROLL CALL (per-feature ritual step 5 — written BEFORE the tests, which is the only
way it finds anything)
======================================================================================
One row per declaration 8c introduces, one column per VALUE it branches on, naming the
fixture that covers it.  An empty cell is the finding.

| declaration / branch            | value                     | fixture                                             |
|---------------------------------|---------------------------|-----------------------------------------------------|
| axis values                     | explicit list             | ``tiny_declaration``                                |
|                                 | ``available`` sentinel    | ``test_the_available_sentinel_resolves_the_sparse_level_set`` |
| axis path                       | plain ``RunConfig`` field | ``tiny_declaration`` (``level``)                    |
|                                 | dotted option path        | ``test_a_dotted_axis_path_sweeps_an_option_dict``   |
| sentinel axis ORDER             | build fixed first         | ``test_the_available_sentinel_resolves_the_sparse_level_set`` |
|                                 | build after / missing     | ``test_the_sentinel_refuses_when_build_is_not_fixed_first`` |
| explicit ``(build, level)``     | exists                    | every run fixture                                   |
|                                 | does NOT exist            | ``test_an_explicit_nonexistent_level_is_refused_not_skipped`` |
| ``base`` ∩ ``axes``             | disjoint                  | every fixture                                       |
|                                 | overlapping               | ``test_a_field_in_both_base_and_axes_is_refused``   |
| ``sweep_schema_version``        | 1                         | every fixture                                       |
|                                 | anything else             | ``test_an_unsupported_declaration_version_is_refused`` |
| axis value TYPE                 | list / sentinel           | above                                               |
|                                 | scalar / empty list       | ``test_a_malformed_axis_is_refused``                |
| ``RecordStore.readable``        | True (clean + cache)      | ``test_the_second_run_of_a_sweep_serves_every_cell_from_cache`` |
|                                 | False (``--no-cache``)    | ``test_no_cache_recomputes_but_still_refreshes_the_shared_store`` |
|                                 | False (dirty tree)        | ``test_a_dirty_tree_refuses_the_cache_AND_the_shared_store`` |
| ``RecordStore.shared``          | True (sound sha)          | the cache tests above                               |
|                                 | False (dirty)             | ``test_a_dirty_tree_refuses_the_cache_AND_the_shared_store`` |
|                                 | False (no sha at all)     | ``test_an_unknown_engine_version_disables_the_cache`` |
| cell ``source``                 | ``computed``              | ``test_a_first_run_computes_every_cell``            |
|                                 | ``cached``                | ``test_the_second_run_of_a_sweep_serves_every_cell_from_cache`` |
| cell ``status``                 | ``ok``                    | ``test_a_first_run_computes_every_cell``            |
|                                 | ``failed``                | ``test_a_failing_cell_is_recorded_and_the_manifest_is_still_written`` |
| manifest ``warnings`` code      | ``engine_dirty``          | ``test_a_dirty_tree_refuses_the_cache_AND_the_shared_store`` |
|                                 | ``engine_unknown``        | ``test_an_unknown_engine_version_disables_the_cache`` |
|                                 | ``precision``             | ``test_the_precision_warning_keys_on_the_DAY_COUNT_not_the_tier_NAME`` |
|                                 | ``heterogeneous_records`` | ``test_heterogeneous_records_are_refused_not_concatenated`` |
|                                 | ``cells_failed``          | ``test_a_failing_cell_is_recorded_and_the_manifest_is_still_written`` |
| frame written?                  | homogeneous → yes         | ``test_the_frame_concatenates_every_cell_under_one_header`` |
|                                 | heterogeneous → NO        | ``test_heterogeneous_records_are_refused_not_concatenated`` |
| ``declaration.source_path``     | inside the repo           | ``test_a_declaration_path_is_recorded_relative_to_the_repo`` |
|                                 | outside the repo          | ``test_a_declaration_path_is_recorded_relative_to_the_repo`` |
| CLI subcommand                  | ``plan``                  | ``test_the_plan_subcommand_simulates_nothing``      |
|                                 | ``run``                   | ``test_the_run_subcommand_exits_nonzero_on_a_failed_cell`` |
| CLI exit code                   | 0 / 1                     | ``test_the_run_subcommand_exits_nonzero_on_a_failed_cell`` |

TWO ROWS THE TABLE EXPOSED THAT THE FIRST DRAFT OF THE CODE GOT WRONG
---------------------------------------------------------------------
Both were found before a test existed, which is what the table is for:

* ``RecordStore`` had ONE refusal where there are TWO.  ``--no-cache`` and a dirty tree
  are different facts — the first says *recompute*, the second says *the sha does not
  identify the code* — and only the second may not write to the shared store.  The first
  draft wrote dirty-tree records into the shared store, where a later CLEAN run would
  have been served them: §10.2's named failure, implemented.
* The ``precision`` warning keyed on ``day_tier == "quick"``, inherited from §9.1's
  record-level rule.  Tier NAMES have no order and ``"custom"`` sits on both sides of
  quick, so a 60-day cell was silently precise enough and a 20,000-day cell would have
  been flagged alongside a 2,000-day one. It keys on the day COUNT.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.evaluation import report as report_module
from src.evaluation.artifact import SCHEMA_VERSION
from src.evaluation.config import DAY_TIERS
from src.evaluation.sweep import (
    CELL_FAILED,
    CELL_OK,
    LEVELS_SENTINEL,
    MANIFEST_KIND,
    MANIFEST_SCHEMA_VERSION,
    MANIFEST_WARNING_CODES,
    SOURCE_CACHED,
    SOURCE_COMPUTED,
    SWEEP_SCHEMA_VERSION,
    RecordStore,
    SweepDeclaration,
    cache_key,
    main,
    registry_fingerprint,
    run_sweep,
    sweep_hash,
)

#: The scheduler's action-economy warnings are noise in a sweep of many days.
logging.disable(logging.WARNING)

#: A fake, SOUND engine version.  Tests that exercise the cache need a clean sha, and
#: the real tree is dirty exactly when someone is editing — which is when the suite
#: runs.  s55/s56 recorded that `test_a_dirty_tree_is_flagged...` therefore only runs
#: mid-edit; these tests take the other route and INJECT the version, so both branches
#: are reachable on a clean checkout and on a dirty one alike.
FAKE_SHA = "a" * 40


@pytest.fixture(autouse=True)
def _sound_engine_version(monkeypatch):
    """Every test in this module runs against an injected engine version.

    ``run_sweep`` and ``Provenance.build`` both read ``report.engine_version``, so one
    patch keeps the manifest's sha and each record's provenance sha consistent — which
    matters, because ``record_summary`` reads the sha back OUT of the record.
    """
    monkeypatch.setattr(report_module, "engine_version", lambda: (FAKE_SHA, False))
    monkeypatch.setattr(report_module, "_ENGINE_VERSION", None)


def declaration(tmp_path: Path, body: str, name: str = "tiny") -> SweepDeclaration:
    path = tmp_path / f"{name}.yaml"
    path.write_text(body, encoding="utf-8")
    return SweepDeclaration.load(path)


TINY = """
sweep_schema_version: 1
name: tiny
description: two cells, a handful of days.
base:
  build: war_angel
  enemy: baseline
  n_days: 8
  seed: 11
axes:
  level: [1, 2]
"""


@pytest.fixture
def tiny_declaration(tmp_path):
    return declaration(tmp_path, TINY)


def do_run(decl, tmp_path, **kwargs):
    kwargs.setdefault("store_root", tmp_path / "records")
    kwargs.setdefault("sweep_root", tmp_path / "sweeps")
    return run_sweep(decl, **kwargs)


# ---------------------------------------------------------------------------
# The declaration (§10.1)
# ---------------------------------------------------------------------------

def test_cells_are_the_product_of_the_axes_in_declaration_order(tmp_path):
    """Cell count is ``prod(len(axis))`` and the order is the declaration's.

    The order affects no NUMBER — each cell carries its own seed and ``simulate``
    builds a fresh generator from it — but it is fixed so a sweep's console output and
    its manifest read the same way twice.
    """
    decl = declaration(tmp_path, """
sweep_schema_version: 1
name: product
base: {enemy: baseline, n_days: 4, seed: 11}
axes:
  build: [war_angel]
  level: [1, 2]
  party_size: [1, 4]
""")
    cells = decl.cells()
    assert len(cells) == 1 * 2 * 2
    assert [c.coordinate for c in cells] == [
        {"build": "war_angel", "level": 1, "party_size": 1},
        {"build": "war_angel", "level": 1, "party_size": 4},
        {"build": "war_angel", "level": 2, "party_size": 1},
        {"build": "war_angel", "level": 2, "party_size": 4},
    ]
    # The coordinate is a DICT, never a string to parse (§10.1, §5.4's rule one layer up).
    assert all(isinstance(c.coordinate, dict) for c in cells)


def test_the_available_sentinel_resolves_the_sparse_level_set(tmp_path):
    """``level: available`` asks the ADAPTER, because level sets are sparse (§2).

    33 of the 60 (build, level) pairs do not exist — pinned by a tripwire in
    ``test_eval_framework.py`` — so a cross-build sweep cannot name a level list, and
    naming one per build would have to be re-edited whenever a build gains a level.
    """
    from src.evaluation.adapters import get_adapter

    decl = declaration(tmp_path, f"""
sweep_schema_version: 1
name: sentinel
base: {{enemy: baseline, n_days: 4, seed: 11}}
axes:
  build: [war_angel]
  level: {LEVELS_SENTINEL}
""")
    levels = [c.coordinate["level"] for c in decl.cells()]
    assert levels == list(get_adapter("war_angel").available_levels())
    assert levels, "fixture precondition: the build must declare at least one level"


def test_the_sentinel_refuses_when_build_is_not_fixed_first(tmp_path):
    """Axis ORDER is load-bearing for the sentinel, and that is an error, not a KeyError.

    ``available`` resolves against the build already fixed, so ``build`` must come from
    ``base`` or from an EARLIER axis.  Stated as a refusal with the reason, because the
    alternative is a stack trace from somewhere inside the product loop.
    """
    with pytest.raises(ValueError, match="Axis order is load-bearing"):
        declaration(tmp_path, f"""
sweep_schema_version: 1
name: misordered
base: {{enemy: baseline, n_days: 4, seed: 11}}
axes:
  level: {LEVELS_SENTINEL}
  build: [war_angel]
""")


def test_the_sentinel_only_means_anything_for_level(tmp_path):
    with pytest.raises(ValueError, match="only means anything for 'level'"):
        declaration(tmp_path, f"""
sweep_schema_version: 1
name: wrong_axis
base: {{build: war_angel, enemy: baseline, n_days: 4, seed: 11}}
axes:
  party_size: {LEVELS_SENTINEL}
""")


def test_a_dotted_axis_path_sweeps_an_option_dict(tmp_path):
    """A build's scenario axes and the enemy's §7 toggles sweep IDENTICALLY.

    That is §3.1's "the same kind of thing" — one object configures one measurement —
    carried up a layer, and it is what lets 8e sweep thresholds against enemy options
    without a second mechanism.
    """
    decl = declaration(tmp_path, """
sweep_schema_version: 1
name: dotted
base: {build: war_angel, level: 13, enemy: baseline, n_days: 4, seed: 11}
axes:
  enemy_options.control: [false, true]
""")
    cells = decl.cells()
    assert [c.config.enemy_options for c in cells] == [{"control": False}, {"control": True}]
    assert [c.coordinate for c in cells] == [
        {"enemy_options.control": False}, {"enemy_options.control": True},
    ]
    # Each cell gets its OWN options dict — a shared nested dict would let a later axis
    # write into a sibling cell.
    assert cells[0].config.enemy_options is not cells[1].config.enemy_options


def test_an_explicit_nonexistent_level_is_refused_not_skipped(tmp_path):
    """§10.1: a sweep that quietly drops cells reports a smaller, cleaner study.

    This is the distinction the ``available`` sentinel exists to make: a build's sparse
    level set is resolved on REQUEST, and a level named by hand that the build does not
    have is a mistake in the declaration, not a cell to skip.
    """
    decl = declaration(tmp_path, """
sweep_schema_version: 1
name: bad_level
base: {build: war_angel, enemy: baseline, n_days: 4, seed: 11}
axes:
  level: [1, 99]
""")
    with pytest.raises(ValueError, match="no level 99"):
        decl.cells()


def test_a_field_in_both_base_and_axes_is_refused(tmp_path):
    """Refused rather than resolved by precedence (§10.1).

    A cell whose value depends on which of two places you read it from is §3.4's
    implicit-enemy failure in a different costume: the provenance block would record a
    value picked by a rule nobody stated.
    """
    with pytest.raises(ValueError, match=r"BOTH 'base' and 'axes'"):
        declaration(tmp_path, """
sweep_schema_version: 1
name: overlap
base: {build: war_angel, level: 1, enemy: baseline, n_days: 4, seed: 11}
axes:
  level: [1, 2]
""")


def test_the_overlap_check_sees_THROUGH_an_option_dict(tmp_path):
    """``base.enemy_options.control`` and the axis ``enemy_options.control`` collide.

    The dormancy question asked of the check itself: a naive implementation compares
    ``base``'s top-level KEYS against the axis names, which are ``enemy_options`` and
    ``enemy_options.control`` — different strings, so the collision is invisible and the
    axis silently overwrites the base value one cell at a time.
    """
    with pytest.raises(ValueError, match=r"enemy_options\.control"):
        declaration(tmp_path, """
sweep_schema_version: 1
name: nested_overlap
base:
  build: war_angel
  level: 13
  enemy: baseline
  n_days: 4
  seed: 11
  enemy_options: {control: true}
axes:
  enemy_options.control: [false, true]
""")


def test_an_incomplete_config_names_the_required_enemy_field(tmp_path):
    """``enemy`` is REQUIRED with no default (§3.4), so the refusal says so.

    A ``TypeError`` about a missing keyword argument would send a reader looking for a
    typo in their YAML; the point is that a default enemy is an implicit enemy.
    """
    decl = declaration(tmp_path, """
sweep_schema_version: 1
name: no_enemy
base: {build: war_angel, n_days: 4, seed: 11}
axes:
  level: [1]
""")
    with pytest.raises(ValueError, match="'enemy' in particular is REQUIRED"):
        decl.cells()


def test_an_unsupported_declaration_version_is_refused(tmp_path):
    with pytest.raises(ValueError, match="sweep_schema_version 2 is not supported"):
        declaration(tmp_path, """
sweep_schema_version: 2
name: future
base: {build: war_angel, enemy: baseline}
axes: {level: [1]}
""")


@pytest.mark.parametrize("axis_body, match", [
    ("level: 1", "must be a list"),
    ("level: []", "is an empty list"),
    ("party_size: 4", "must be a list"),
])
def test_a_malformed_axis_is_refused(tmp_path, axis_body, match):
    with pytest.raises(ValueError, match=match):
        declaration(tmp_path, f"""
sweep_schema_version: 1
name: malformed
base: {{build: war_angel, enemy: baseline, n_days: 4, seed: 11}}
axes:
  {axis_body}
""")


def test_an_unknown_field_is_refused_on_both_sides(tmp_path):
    for where in ("base", "axes"):
        body = {
            "base": "base: {build: war_angel, enemy: baseline, nonsense: 3}\naxes: {level: [1]}",
            "axes": "base: {build: war_angel, enemy: baseline}\naxes: {nonsense: [3]}",
        }[where]
        with pytest.raises(ValueError, match="not a\n?.*RunConfig field"):
            declaration(tmp_path, f"sweep_schema_version: 1\nname: unknown\n{body}")


def test_a_declaration_with_no_axes_is_refused(tmp_path):
    with pytest.raises(ValueError, match="declares no axes"):
        declaration(tmp_path, """
sweep_schema_version: 1
name: axisless
base: {build: war_angel, level: 1, enemy: baseline}
axes: {}
""")


def test_an_unknown_declaration_key_is_refused(tmp_path):
    """The declaration is a CLOSED schema (§10.1), so a typo is an error.

    An ignored key is the worst outcome available: the sweep runs, looks right, and
    silently does not do the thing the extra key asked for.
    """
    with pytest.raises(ValueError, match="Unknown sweep declaration key"):
        declaration(tmp_path, """
sweep_schema_version: 1
name: typo
bases: {build: war_angel}
axes: {level: [1]}
""")


# ---------------------------------------------------------------------------
# Identity (§10.1)
# ---------------------------------------------------------------------------

def test_sweep_identity_EXCLUDES_the_engine_and_the_cache_key_INCLUDES_it(tmp_path,
                                                                         tiny_declaration):
    """§10.1's split, asserted on both halves.

    ``sweep_hash`` is over WHICH MEASUREMENTS the sweep asks for, so a sweep re-run at a
    new engine version keeps its id and its directory; ``cache_key`` is over whether a
    stored record is still VALID, so it must move.  The precedent is in the codebase:
    ``artifact.run_id`` leaves the commit out for the same reason.
    """
    cells = tiny_declaration.cells()
    assert sweep_hash(cells) == sweep_hash(cells)
    first = cache_key(cells[0].config, "a" * 40)
    second = cache_key(cells[0].config, "b" * 40)
    assert first != second
    assert first.startswith(cells[0].config.config_hash())
    # Identity does not move with the engine; validity does.
    assert sweep_hash(cells) not in (first, second)


def test_two_cells_of_one_sweep_cannot_share_a_cache_key(tiny_declaration):
    cells = tiny_declaration.cells()
    keys = {cache_key(c.config, FAKE_SHA) for c in cells}
    assert len(keys) == len(cells)


def test_cache_key_refuses_to_key_on_the_config_alone():
    """Without a sha the key cannot say WHICH code produced the record.

    So it raises rather than returning a config-only key that would look like a valid
    cache entry; ``run_sweep`` disables the store in that case instead.
    """
    from src.evaluation import RunConfig

    config = RunConfig(build="war_angel", level=1, enemy="baseline", n_days=4)
    with pytest.raises(ValueError, match="needs an engine_commit"):
        cache_key(config, None)


def test_the_registry_fingerprint_counts_DECLARATIONS(tmp_path):
    """Declarations, not rows — the unit the periodic metric-set review counts.

    Same call s52 made and the user confirmed. A registry missing a declaration must
    fingerprint differently, or the manifest cannot detect a mixed sweep.
    """
    from src.evaluation.metrics import METRICS, MetricRegistry

    assert registry_fingerprint(METRICS) == registry_fingerprint(METRICS)
    reduced = MetricRegistry(definitions=METRICS.scalars()[:3])
    assert registry_fingerprint(reduced) != registry_fingerprint(METRICS)


# ---------------------------------------------------------------------------
# Running (§10.2)
# ---------------------------------------------------------------------------

def test_a_first_run_computes_every_cell(tmp_path, tiny_declaration):
    result = do_run(tiny_declaration, tmp_path)
    assert [c["status"] for c in result.cells] == [CELL_OK, CELL_OK]
    assert [c["source"] for c in result.cells] == [SOURCE_COMPUTED, SOURCE_COMPUTED]
    assert result.manifest["cache"]["hits"] == 0
    assert result.manifest["cache"]["misses"] == 2
    assert result.manifest["cache"]["shared"] is True


def test_the_manifest_counts_agree_with_its_own_cell_list(tmp_path, tiny_declaration):
    """Ritual step 6's lesson as an ASSERTION: look first at whatever claims to
    summarize or count the rest of the output.

    Four of the six defects that step has found were in a renderer or a summary layer,
    and s52's was a top-level count that read half its set.  A manifest is almost
    entirely summary, so every number it states about itself is checked against the
    list it describes — by addition, so the buckets have to partition.
    """
    result = do_run(tiny_declaration, tmp_path)
    manifest = result.manifest
    assert manifest["n_cells"] == len(manifest["cells"])
    ok = [c for c in manifest["cells"] if c["status"] == CELL_OK]
    assert manifest["cache"]["hits"] + manifest["cache"]["misses"] == len(ok)
    assert manifest["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["kind"] == MANIFEST_KIND
    assert manifest["record_schema_version"] == SCHEMA_VERSION
    assert manifest["axes"] == list(tiny_declaration.axes)
    assert all(w["code"] in MANIFEST_WARNING_CODES for w in manifest["warnings"])


def test_every_cell_points_at_a_record_that_exists(tmp_path, tiny_declaration):
    """``record`` is relative to the MANIFEST, so a sweep directory can be moved.

    That is §9's line about the sim never knowing the website: an absolute path would
    bind the artifact to the machine that produced it.
    """
    result = do_run(tiny_declaration, tmp_path)
    for cell in result.cells:
        assert not Path(cell["record"]).is_absolute()
        target = (result.manifest_path.parent / cell["record"]).resolve()
        assert target.exists()
        record = json.loads(target.read_text())
        assert record["run_id"] == cell["run_id"]
        assert record["schema_version"] == cell["schema_version"]


def test_the_second_run_of_a_sweep_serves_every_cell_from_cache(tmp_path, tiny_declaration):
    """§10's whole point: re-running a sweep recomputes only what changed.

    Asserted on the CACHE COUNTERS rather than on a timing, and separately on the
    records' modification times — a hit that silently recomputed would still report a
    hit if only the counter were checked.
    """
    first = do_run(tiny_declaration, tmp_path)
    keys = [c["cache_key"] for c in first.cells]
    store = first.store
    stamps = {k: store.json_path(k).stat().st_mtime_ns for k in keys}

    second = do_run(tiny_declaration, tmp_path)
    assert [c["source"] for c in second.cells] == [SOURCE_CACHED, SOURCE_CACHED]
    assert second.manifest["cache"]["hits"] == 2
    assert second.manifest["cache"]["misses"] == 0
    assert {k: store.json_path(k).stat().st_mtime_ns for k in keys} == stamps
    # Same study, same id, same directory — identity excludes the engine AND the cache.
    assert second.sweep_id == first.sweep_id
    assert second.directory == first.directory


def test_a_changed_engine_version_is_a_MISS_and_does_not_overwrite(tmp_path,
                                                                   tiny_declaration,
                                                                   monkeypatch):
    """The property that makes the shared store engine-change-safe (§10.2).

    The sha is in the FILENAME, so a new commit writes a new record beside the old one.
    The per-sweep alternative lacks this: ``artifact.run_id`` carries no engine
    component, so stemming records on it overwrites the earlier record silently.
    """
    first = do_run(tiny_declaration, tmp_path)
    old_keys = {c["cache_key"] for c in first.cells}

    monkeypatch.setattr(report_module, "engine_version", lambda: ("b" * 40, False))
    second = do_run(tiny_declaration, tmp_path)
    new_keys = {c["cache_key"] for c in second.cells}

    assert [c["source"] for c in second.cells] == [SOURCE_COMPUTED, SOURCE_COMPUTED]
    assert not (old_keys & new_keys)
    store_root = tmp_path / "records"
    assert all((store_root / f"{k}.json").exists() for k in old_keys | new_keys)


def test_no_cache_recomputes_but_still_refreshes_the_shared_store(tmp_path,
                                                                  tiny_declaration):
    """``--no-cache`` says RECOMPUTE; it does not say the sha is untrustworthy.

    So the fresh records go to the SHARED store, and a later ordinary run is served
    them.  Collapsing this with the dirty-tree refusal was the first draft's bug — the
    roll call found it before a test existed.
    """
    first = do_run(tiny_declaration, tmp_path)
    keys = [c["cache_key"] for c in first.cells]
    stamps = {k: (tmp_path / "records" / f"{k}.json").stat().st_mtime_ns for k in keys}

    second = do_run(tiny_declaration, tmp_path, use_cache=False)
    assert [c["source"] for c in second.cells] == [SOURCE_COMPUTED, SOURCE_COMPUTED]
    assert second.manifest["cache"]["shared"] is True
    assert second.manifest["cache"]["store"] == str(tmp_path / "records")
    assert "--no-cache" in second.manifest["cache"]["disabled_reason"]
    # Rewritten in place, in the shared store — same keys, new mtimes.
    assert [c["cache_key"] for c in second.cells] == keys
    assert {k: (tmp_path / "records" / f"{k}.json").stat().st_mtime_ns
            for k in keys} != stamps
    # And a THIRD, ordinary run is served from the refreshed store.
    third = do_run(tiny_declaration, tmp_path)
    assert [c["source"] for c in third.cells] == [SOURCE_CACHED, SOURCE_CACHED]
    # `--no-cache` is not a comparability problem, so it raises no warning.
    assert "engine_dirty" not in second.warning_codes


def test_a_dirty_tree_refuses_the_cache_AND_the_shared_store(tmp_path, tiny_declaration,
                                                             monkeypatch):
    """§10.2: a dirty sha makes neither a read NOR a write sound.

    A record written from uncommitted work is indistinguishable from one written at
    that commit, so writing it to the shared store would serve it to a later CLEAN run.
    Those records go beside the sweep's own manifest instead, which keeps the sweep
    usable and the shared store trustworthy.
    """
    monkeypatch.setattr(report_module, "engine_version", lambda: (FAKE_SHA, True))
    result = do_run(tiny_declaration, tmp_path)

    assert result.manifest["engine_dirty"] is True
    assert "engine_dirty" in result.warning_codes
    assert result.manifest["cache"]["shared"] is False
    assert result.manifest["cache"]["hits"] == 0
    # NOTHING reached the shared store — not even the directory.
    assert not (tmp_path / "records").exists()
    for cell in result.cells:
        target = (result.manifest_path.parent / cell["record"]).resolve()
        assert target.exists()
        assert result.directory in target.parents

    # And a dirty run never serves a hit to itself on a second pass.
    again = do_run(tiny_declaration, tmp_path)
    assert [c["source"] for c in again.cells] == [SOURCE_COMPUTED, SOURCE_COMPUTED]


def test_an_unknown_engine_version_disables_the_cache(tmp_path, tiny_declaration,
                                                      monkeypatch):
    """Outside a git checkout the code version is unknown, so the key cannot be formed.

    ``engine_version`` returns ``(None, False)`` there rather than raising — "an
    exploratory run in a tarball should still produce a report" — and the sweep layer
    honours that: it still produces its records, keyed ``<config_hash>-unknown`` beside
    its own manifest, and says in a warning that the version is unknown.
    """
    monkeypatch.setattr(report_module, "engine_version", lambda: (None, False))
    result = do_run(tiny_declaration, tmp_path)

    assert "engine_unknown" in result.warning_codes
    assert result.manifest["engine_commit"] is None
    assert result.manifest["cache"]["shared"] is False
    assert all(c["cache_key"].endswith("-unknown") for c in result.cells)
    assert all(c["status"] == CELL_OK for c in result.cells)
    assert not (tmp_path / "records").exists()


def test_the_precision_warning_keys_on_the_DAY_COUNT_not_the_tier_NAME(tmp_path,
                                                                        monkeypatch):
    """Tier NAMES have no order; ``"custom"`` sits on BOTH sides of quick.

    Found by rendering one real output (ritual step 6) on a 60-day smoke sweep, which
    the name-keyed first draft passed in silence.  The three cells here are the branch:
    below quick, exactly quick, and above it.  A sweep is the shape that makes this
    reachable, because one declaration can span the tiers.

    The quick tier is shrunk to 10 days FOR THIS TEST, which is also the honest framing:
    what is under test is the ORDERING of the three cells around the tier, not the value
    2,000.  Simulating 6,008 days to assert a string would have cost ~15s of a suite
    that already runs six minutes, and ``DAY_TIERS`` is the one dict both
    ``RunConfig.day_tier`` and the warning read, so one ``setitem`` moves both together.
    """
    monkeypatch.setitem(DAY_TIERS, "quick", 10)
    decl = declaration(tmp_path, f"""
sweep_schema_version: 1
name: tiers
base: {{build: war_angel, level: 1, enemy: baseline, seed: 11}}
axes:
  n_days: [8, {DAY_TIERS['quick']}, {DAY_TIERS['quick'] * 2}]
""")
    cells = decl.cells()
    assert [c.config.day_tier for c in cells] == ["custom", "quick", "custom"], (
        "fixture precondition: the three cells must be below / at / above the quick "
        "tier, and the two 'custom' names must sit on OPPOSITE sides of it — which is "
        "the whole reason the name cannot be the key"
    )
    result = do_run(decl, tmp_path)
    warning = next(w for w in result.manifest["warnings"] if w["code"] == "precision")
    assert "2 of 3" in warning["message"]
    assert "Smallest: 8 days" in warning["message"]


def test_a_sweep_entirely_above_the_quick_tier_raises_no_precision_warning(tmp_path,
                                                                           monkeypatch):
    monkeypatch.setitem(DAY_TIERS, "quick", 10)
    decl = declaration(tmp_path, f"""
sweep_schema_version: 1
name: fine
base: {{build: war_angel, level: 1, enemy: baseline, seed: 11}}
axes:
  n_days: [{DAY_TIERS['quick'] + 1}]
""")
    result = do_run(decl, tmp_path)
    assert "precision" not in result.warning_codes


def test_a_failing_cell_is_recorded_and_the_manifest_is_still_written(tmp_path,
                                                                     tiny_declaration,
                                                                     monkeypatch):
    """A 48-cell study must not lose 47 results to a crash in the 48th.

    So the failure is RECORDED per cell with its exception text, the ``cells_failed``
    warning names the coordinates, the manifest is written — and the CLI exits non-zero,
    because a partial sweep that reports success is worse than one that crashes.
    """
    from src.evaluation import runner as runner_module

    real = runner_module.run
    calls = {"n": 0}

    def flaky(config, **kwargs):
        calls["n"] += 1
        if config.level == 2:
            raise RuntimeError("injected")
        return real(config, **kwargs)

    monkeypatch.setattr(runner_module, "run", flaky)
    result = do_run(tiny_declaration, tmp_path)

    assert calls["n"] == 2, "fixture precondition: both cells must have been attempted"
    assert [c["status"] for c in result.cells] == [CELL_OK, CELL_FAILED]
    assert result.cells[1]["note"] == "RuntimeError: injected"
    assert result.cells[1]["record"] is None
    assert "cells_failed" in result.warning_codes
    assert "{level=2}" in next(w["message"] for w in result.manifest["warnings"]
                               if w["code"] == "cells_failed")
    assert result.manifest_path.exists()
    # The surviving cell is still in the frame.
    assert result.frame_path is not None
    assert result.frame_path.read_text().count("war_angel@L1") > 0


def test_the_frame_concatenates_every_cell_under_one_header(tmp_path, tiny_declaration):
    """The tidy frame is ONE header plus every cell's rows (§9.1's sweep CSV).

    The run-identifying columns repeat on every row, which is exactly what makes a
    sweep's records concatenate into one frame that ``group_by(run_id)`` splits again.
    """
    import csv

    result = do_run(tiny_declaration, tmp_path)
    rows = list(csv.DictReader(result.frame_path.open()))
    by_run: dict[str, int] = {}
    for row in rows:
        by_run[row["run_id"]] = by_run.get(row["run_id"], 0) + 1
    assert set(by_run) == {c["run_id"] for c in result.cells}
    assert len(set(by_run.values())) == 1, "every cell contributes the same row count"
    assert result.frame_path.read_text().count("run_id,config_hash") == 1


def test_heterogeneous_records_are_refused_not_concatenated(tmp_path, tiny_declaration):
    """§10.2: two registries' records are both valid and not comparable.

    ``write_sweep_csv`` already raises when two reports' columns differ; s57 promotes
    that from an incidental column error into a manifest check that NAMES the cells
    which differ — and then declines to write the frame, because a frame whose columns
    meant different things in different blocks is two frames stacked and nothing
    downstream could tell.

    Synthetic, like §9.1's ``coverage_gap`` detector: one stored record's header is
    doctored so the branch is a TESTED value rather than a retained one.
    """
    first = do_run(tiny_declaration, tmp_path)
    assert first.frame_path is not None, "precondition: a homogeneous sweep writes one"

    doctored = tmp_path / "records" / f"{first.cells[0]['cache_key']}.csv"
    lines = doctored.read_text().split("\n")
    lines[0] = lines[0] + ",an_extra_column"
    doctored.write_text("\n".join(lines))

    second = do_run(tiny_declaration, tmp_path)
    assert "heterogeneous_records" in second.warning_codes
    message = next(w["message"] for w in second.manifest["warnings"]
                   if w["code"] == "heterogeneous_records")
    assert "2 different tidy-CSV headers" in message
    assert "{level=1}" in message or "{level=2}" in message
    assert second.frame_path is None, "a mixed frame must not be written"
    assert second.manifest_path.exists(), "the manifest IS what names the mismatch"


def test_a_half_written_store_entry_is_not_a_hit(tmp_path, tiny_declaration):
    """A JSON without its CSV would leave the frame short one cell with no error."""
    first = do_run(tiny_declaration, tmp_path)
    key = first.cells[0]["cache_key"]
    (tmp_path / "records" / f"{key}.csv").unlink()

    store = RecordStore(root=tmp_path / "records")
    assert store.has(key) is False
    second = do_run(tiny_declaration, tmp_path)
    assert second.cells[0]["source"] == SOURCE_COMPUTED
    assert second.cells[1]["source"] == SOURCE_CACHED


def test_a_declaration_path_is_recorded_relative_to_the_repo(tmp_path, tiny_declaration):
    """An ABSOLUTE path in a committed artifact resolves for one person on one machine.

    Found by eye (ritual step 6): the first draft wrote ``str(source_path)``, putting a
    scratchpad path into the field that says where the study was declared.  Inside the
    repo it is repo-relative; outside it, the name is all that can be said honestly.
    """
    outside = tiny_declaration.to_dict()["source_path"]
    assert outside == "tiny.yaml", outside

    inside = SweepDeclaration.load("sweeps/war_angel_levels.yaml")
    assert inside.to_dict()["source_path"] == "sweeps/war_angel_levels.yaml"


def test_the_shipped_declaration_resolves(tmp_path):
    """The committed declaration is checked, not just committed.

    A declaration nobody has resolved is a file that looks like a study; this is the
    cheap guard that its axes, its sentinel and its enemy kind are all valid.
    """
    decl = SweepDeclaration.load("sweeps/war_angel_levels.yaml")
    cells = decl.cells()
    assert len(cells) == len(decl.cells())
    assert {c.config.build for c in cells} == {"war_angel"}
    assert all(c.config.enemy == "baseline" for c in cells)
    # STANDARD, not quick, since s62: the definitive #6b run must not publish an
    # artifact carrying §9.1's `precision` warning, and a level sweep gets no
    # pairing benefit (every level draws its own `(purpose, owner)` substream
    # because the character is named `WarAngel-L{level}`), so each cell's interval
    # has to be bought with days rather than with common random numbers.
    assert all(c.config.day_tier == "standard" for c in cells)
    assert decl.schema_version == SWEEP_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_the_plan_subcommand_simulates_nothing(tmp_path, capsys, monkeypatch):
    """``plan`` is how you check a declaration's cell count before spending hours.

    It is as STRICT as ``run`` — resolution validates every config — but it must not
    simulate, which is asserted by making a simulation an error.
    """
    from src.evaluation import runner as runner_module

    def forbidden(*args, **kwargs):                  # pragma: no cover - must not run
        raise AssertionError("plan must not simulate")

    monkeypatch.setattr(runner_module, "run", forbidden)
    path = tmp_path / "tiny.yaml"
    path.write_text(TINY, encoding="utf-8")

    assert main(["plan", str(path)]) == 0
    out = capsys.readouterr().out
    assert "2 cells" in out
    assert "total days: 16" in out
    assert "{level=1}" in out and "{level=2}" in out


def test_the_run_subcommand_exits_nonzero_on_a_failed_cell(tmp_path, capsys, monkeypatch):
    from src.evaluation import runner as runner_module

    path = tmp_path / "tiny.yaml"
    path.write_text(TINY, encoding="utf-8")
    args = ["run", str(path), "--store", str(tmp_path / "r"), "--out", str(tmp_path / "s")]

    assert main(args) == 0
    assert "2 hit(s)" not in capsys.readouterr().out

    monkeypatch.setattr(runner_module, "run",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert main(args + ["--no-cache"]) == 1
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "WARNING [cells_failed]" in out


def test_the_cli_does_not_report_MISSES_when_the_cache_was_never_consulted(
        tmp_path, capsys, monkeypatch):
    """"0 hit(s), 16 miss(es)" reads as sixteen keys that failed to match.

    Found by eye on the real 16-level sweep (ritual step 6): the counters were right and
    the sentence was wrong, which is four of the six defects that step has found. A
    disabled cache was never consulted, so it reports the refusal and the cell count.
    """
    monkeypatch.setattr(report_module, "engine_version", lambda: (FAKE_SHA, True))
    path = tmp_path / "tiny.yaml"
    path.write_text(TINY, encoding="utf-8")
    assert main(["run", str(path), "--store", str(tmp_path / "r"),
                 "--out", str(tmp_path / "s")]) == 0
    out = capsys.readouterr().out
    assert "cache:    DISABLED" in out
    assert "2 cell(s) computed" in out
    assert "miss(es)" not in out


def test_the_cli_reports_cache_hits_on_the_second_run(tmp_path, capsys):
    path = tmp_path / "tiny.yaml"
    path.write_text(TINY, encoding="utf-8")
    args = ["run", str(path), "--store", str(tmp_path / "r"), "--out", str(tmp_path / "s")]
    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "cache:    2 hit(s), 0 miss(es)" in out
