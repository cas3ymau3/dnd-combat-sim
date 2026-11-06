"""
sweep.py — the sweep driver: declaration -> cells -> records -> manifest (§10, §10.1-10.2).

§9.1 says a sweep *is* "a directory of run records plus a manifest"; §10 says sweeps are
*declared* in YAML.  Those are two objects and this module is the hinge between them:

```
sweeps/foo.yaml  ->  SweepDeclaration  ->  [SweepCell]  ->  records/<key>.{json,csv}
                                                        ->  sweeps/<id>/manifest.json
                                                        ->  sweeps/<id>/<name>.csv
```

**The shape was LOCKED in §10.1 before this file existed**, per the per-feature ritual's
step 4 and on the §9.1 precedent — that schema was locked ahead of its writer and then
absorbed three additions at ``schema_version`` 1 without a break.  Everything this module
serializes is specified there; what lives here is the mechanism.

Three versions, three objects
-----------------------------
:data:`SWEEP_SCHEMA_VERSION` (the declaration), :data:`MANIFEST_SCHEMA_VERSION` (the
manifest) and ``artifact.SCHEMA_VERSION`` (one run record) are SEPARATE (user, s57).
Three consumers with three churn rates: a manifest field added next session must not
force a bump on the record, which would cost the record's comparability story for a
field nothing is built against.  The record's version is quoted per CELL inside the
manifest, which is what makes a mixed-version sweep detectable instead of silently
absorbed.

Why cached and computed cells share ONE renderer
------------------------------------------------
A cache hit has no :class:`EvalReport` — only the serialized record.  The tempting shape
is to concatenate the tidy frame from reports for computed cells and from the stored JSON
for cached ones, which is **two renderers for one quantity**: the s54 seam check's exact
shape, and it would drift within two sessions.  So the store holds BOTH halves of
``write_artifact``'s output (``<key>.json`` and ``<key>.csv``), the per-record CSV is
rendered ONCE by ``artifact.report_to_rows`` at compute time, and concatenation is
file-level for every cell alike.  A pleasant consequence: comparing the stored header
lines IS the heterogeneous-registry check §10.2 asks for, with no extra machinery.

A declaration error is NOT a failed cell
----------------------------------------
Cell resolution calls ``RunConfig.validate()``, so an unknown axis, a nonexistent
explicit ``(build, level)`` pair or an unknown build option is refused BEFORE any day is
simulated — ``plan`` is as strict as ``run``.  :data:`CELL_FAILED` is therefore only ever
a RUNTIME failure, and a sweep that hits one still writes its manifest (a 48-cell study
must not lose 47 results to a crash in the 48th) while the CLI exits non-zero, because a
partial sweep that reports success is worse than one that crashes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Sequence

from . import artifact as artifact_module
from .config import DAY_TIERS, RunConfig
from .metrics import METRICS, MetricRegistry

if TYPE_CHECKING:                                    # pragma: no cover
    from .report import EvalReport

#: §10.1.  Bump only for a declaration change a version-1 reader could not survive.
SWEEP_SCHEMA_VERSION = 1

#: §10.1.  Separate from the declaration's and from the record's (user, s57).
MANIFEST_SCHEMA_VERSION = 1

MANIFEST_KIND = "sweep_manifest"

#: The ``level: available`` sentinel (§10.1).  Level sets are SPARSE (§2) — 33 of the 60
#: (build, level) pairs do not exist — so a cross-build sweep cannot name a level list.
LEVELS_SENTINEL = "available"

#: Axis-name prefixes that address a nested option dict rather than a scalar field.
#: A build's own scenario axes and the enemy's §7 toggles sweep IDENTICALLY, which is
#: §3.1's "the same kind of thing" carried up one layer.
OPTION_FIELDS = ("build_options", "enemy_options")

#: Where a cell's record came from on THIS invocation.
SOURCE_COMPUTED = "computed"
SOURCE_CACHED = "cached"
SOURCES = (SOURCE_COMPUTED, SOURCE_CACHED)

#: Whether a cell produced a record at all.  See the module docstring: this is a
#: RUNTIME outcome; a bad declaration never gets this far.
CELL_OK = "ok"
CELL_FAILED = "failed"
CELL_STATUSES = (CELL_OK, CELL_FAILED)

#: Closed warning vocabulary for the manifest, the same contract §9.1's ``warnings``
#: array gives a run record: a reader who must open a nested block to learn that a
#: result is not comparable will not open it.
MANIFEST_WARNING_CODES: dict[str, str] = {
    "engine_dirty": "the working tree had uncommitted changes: the cache is disabled "
                    "and no cell is reproducible from its engine_commit",
    "engine_unknown": "no git checkout was found, so the code version is unknown and "
                      "the cache is disabled",
    "precision": "at least one cell ran at the 'quick' tier — iteration runs, not "
                 "publishable ones",
    "heterogeneous_records": "cells were produced under different metric registries or "
                             "record schema versions and must not be pooled",
    "cells_failed": "at least one cell raised and produced no record",
}


# ---------------------------------------------------------------------------
# The declaration (§10.1)
# ---------------------------------------------------------------------------

def _split_path(name: str) -> "tuple[str, str | None]":
    """``"build_options.zone_effect"`` -> ``("build_options", "zone_effect")``."""
    if "." not in name:
        return name, None
    prefix, _, key = name.partition(".")
    if prefix not in OPTION_FIELDS:
        raise ValueError(
            f"Axis/base path {name!r} is dotted, but {prefix!r} is not an option dict. "
            f"Only {OPTION_FIELDS} take a dotted path."
        )
    if not key or "." in key:
        raise ValueError(f"Axis/base path {name!r} must be exactly '<dict>.<option>'.")
    return prefix, key


def _run_config_fields() -> frozenset[str]:
    import dataclasses
    return frozenset(f.name for f in dataclasses.fields(RunConfig))


def _set_path(partial: dict[str, Any], name: str, value: Any) -> dict[str, Any]:
    """A COPY of ``partial`` with ``name`` set — nested dicts copied, not mutated.

    Copying matters because the cell product fans one partial out into many, and a
    shared nested dict would let a later axis write into a sibling cell's options.
    """
    prefix, key = _split_path(name)
    out = dict(partial)
    if key is None:
        out[prefix] = value
    else:
        nested = dict(out.get(prefix) or {})
        nested[key] = value
        out[prefix] = nested
    return out


@dataclass(frozen=True)
class SweepDeclaration:
    """One parsed ``sweeps/*.yaml`` (§10.1): which measurements to take.

    Validated on construction, so a malformed declaration fails at load rather than
    halfway through a study.
    """

    name: str
    base: dict[str, Any]
    #: Ordered — ``dict`` preserves insertion order, and the order is LOAD-BEARING
    #: because ``level: available`` resolves against the ``build`` already fixed.
    axes: dict[str, Any]
    description: str = ""
    schema_version: int = SWEEP_SCHEMA_VERSION
    source_path: "Path | None" = None

    def __post_init__(self) -> None:
        if self.schema_version != SWEEP_SCHEMA_VERSION:
            raise ValueError(
                f"sweep_schema_version {self.schema_version} is not supported "
                f"(this build reads {SWEEP_SCHEMA_VERSION})."
            )
        if not self.name or not isinstance(self.name, str):
            raise ValueError("A sweep declaration needs a non-empty 'name'.")
        if not self.axes:
            raise ValueError(
                f"Sweep {self.name!r} declares no axes. A sweep with no axes is one "
                "run — use evaluation.run for that."
            )

        fields = _run_config_fields()
        for where, names in (("base", self.base), ("axes", self.axes)):
            for raw in names:
                prefix, _ = _split_path(raw)
                if prefix not in fields:
                    raise ValueError(
                        f"Sweep {self.name!r} {where} names {raw!r}, which is not a "
                        f"RunConfig field. Known: {sorted(fields)}."
                    )

        # A field in BOTH base and axes is an ERROR, not an override: a cell whose
        # value depends on which of two places you read is §3.4's implicit-enemy
        # failure in a different costume.
        overlap = sorted(set(self._base_paths()) & set(self.axes))
        if overlap:
            raise ValueError(
                f"Sweep {self.name!r} sets {overlap} in BOTH 'base' and 'axes'. That is "
                "refused rather than resolved by precedence: a cell whose value depends "
                "on which of two places you read it from is exactly the implicit "
                "assumption §3.4 exists to remove. Name it once."
            )

        for axis, values in self.axes.items():
            if values == LEVELS_SENTINEL:
                if axis != "level":
                    raise ValueError(
                        f"Sweep {self.name!r} axis {axis!r} uses the "
                        f"{LEVELS_SENTINEL!r} sentinel, which only means anything for "
                        "'level' (it resolves the build's sparse level set)."
                    )
                continue
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise ValueError(
                    f"Sweep {self.name!r} axis {axis!r} must be a list of values"
                    + (f" or {LEVELS_SENTINEL!r}" if axis == "level" else "")
                    + f"; got {values!r}."
                )
            if not values:
                raise ValueError(f"Sweep {self.name!r} axis {axis!r} is an empty list.")

        if self.axes.get("level") == LEVELS_SENTINEL:
            # Axis ORDER is load-bearing, and this is the one place it can be stated
            # as an error instead of discovered as a KeyError.
            axis_order = list(self.axes)
            if "build" not in self.base and (
                "build" not in axis_order
                or axis_order.index("build") > axis_order.index("level")
            ):
                raise ValueError(
                    f"Sweep {self.name!r} resolves 'level' from the build's sparse "
                    f"level set, so 'build' must be fixed first — either in 'base' or "
                    f"as an EARLIER axis. Axis order is load-bearing here; got "
                    f"{axis_order}."
                )

    # -- loading ----------------------------------------------------------

    def _base_paths(self) -> list[str]:
        """``base`` flattened to the same dotted-path vocabulary ``axes`` uses."""
        paths: list[str] = []
        for name, value in self.base.items():
            if name in OPTION_FIELDS and isinstance(value, dict):
                paths.extend(f"{name}.{key}" for key in value)
            else:
                paths.append(name)
        return paths

    @classmethod
    def from_dict(cls, data: dict[str, Any], *,
                  source_path: "Path | None" = None) -> "SweepDeclaration":
        if not isinstance(data, dict):
            raise ValueError(f"A sweep declaration must be a YAML mapping; got {type(data)}.")
        unknown = sorted(set(data) - {"sweep_schema_version", "name", "description",
                                      "base", "axes"})
        if unknown:
            raise ValueError(
                f"Unknown sweep declaration key(s) {unknown}. A declaration is a closed "
                "schema (§10.1): sweep_schema_version / name / description / base / axes."
            )
        return cls(
            name=data.get("name", ""),
            base=dict(data.get("base") or {}),
            axes=dict(data.get("axes") or {}),
            description=str(data.get("description", "")),
            schema_version=int(data.get("sweep_schema_version", SWEEP_SCHEMA_VERSION)),
            source_path=source_path,
        )

    @classmethod
    def load(cls, path: "str | Path") -> "SweepDeclaration":
        import yaml

        target = Path(path)
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        return cls.from_dict(data, source_path=target)

    def to_dict(self) -> dict[str, Any]:
        """The declaration as the manifest embeds it — verbatim, so the manifest
        records what was ASKED as well as what was taken."""
        return {
            "sweep_schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "base": self.base,
            "axes": {k: (v if v == LEVELS_SENTINEL else list(v))
                     for k, v in self.axes.items()},
            "source_path": _repo_relative(self.source_path),
        }

    # -- cells ------------------------------------------------------------

    def _axis_values(self, axis: str, values: Any, partial: dict[str, Any]) -> list[Any]:
        if values != LEVELS_SENTINEL:
            return list(values)
        from .adapters import get_adapter

        build = partial.get("build")
        if build is None:                            # pragma: no cover - __post_init__
            raise ValueError(
                f"Sweep {self.name!r}: 'level: {LEVELS_SENTINEL}' needs 'build' fixed first."
            )
        return list(get_adapter(build).available_levels())

    def cells(self) -> list["SweepCell"]:
        """Resolve the declaration into its cells, in declaration-product order.

        Every cell's ``RunConfig`` is VALIDATED here, which is what makes ``plan`` as
        strict as ``run``: a nonexistent explicitly-named ``(build, level)`` pair, an
        unknown build option or a bad enemy kind is refused before a single day is
        simulated.  §10.1: a sweep that quietly drops a third of its cells reports a
        smaller, cleaner-looking study than the one that was asked for.
        """
        partials: list[tuple[dict[str, Any], dict[str, Any]]] = [(dict(self.base), {})]
        for axis, values in self.axes.items():
            grown: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for partial, coordinate in partials:
                for value in self._axis_values(axis, values, partial):
                    grown.append((
                        _set_path(partial, axis, value),
                        {**coordinate, axis: value},
                    ))
            partials = grown

        cells: list[SweepCell] = []
        for partial, coordinate in partials:
            try:
                config = RunConfig(**partial)
            except TypeError as exc:
                raise ValueError(
                    f"Sweep {self.name!r} cell {coordinate} does not specify a complete "
                    f"RunConfig: {exc}. 'enemy' in particular is REQUIRED and has no "
                    "default (§3.4) — declare it in 'base' or as an axis."
                ) from None
            config.validate()
            cells.append(SweepCell(coordinate=coordinate, config=config))
        return cells

    def cell_count(self) -> int:
        """Cells WITHOUT resolving configs — what ``plan`` prints first.

        Cheap for every axis but ``level: available``, which has to ask each build.
        """
        return len(self.cells())


@dataclass(frozen=True)
class SweepCell:
    """One cell: an axis coordinate and the ``RunConfig`` it resolves to.

    ``coordinate`` is a DICT, never a string to parse (§10.1).  This is §5.4's rule —
    the one that cost a registry rewrite in s46, when 25 of 51 entries had flattened a
    key into a metric NAME — applied one layer up: a consumer groups by
    ``coordinate["level"]`` and nothing anywhere parses ``war_angel@L13`` apart again.
    """

    coordinate: dict[str, Any]
    config: RunConfig


# ---------------------------------------------------------------------------
# The record store (§10.2)
# ---------------------------------------------------------------------------

def cache_key(config: RunConfig, engine_commit: "str | None") -> str:
    """§10's cache key: ``(config_hash, engine_commit)``, as one filename stem.

    The sha is in the KEY, so an engine change is a miss — and because the key is the
    filename, a new commit writes a new record BESIDE the old one rather than over it.
    That is the property the per-sweep alternative lacks: ``artifact.run_id`` carries no
    engine component, so stemming records on it silently overwrites the earlier record
    after an engine change.

    ``resolved`` is deliberately NOT in here (§10.2): it is a pure function of the
    declared config and the repo contents, both of which this key already holds, so
    hashing it would add nothing and a key you can only compute by doing half the work
    is worth less than one you can compute from the declaration.
    """
    if engine_commit is None:
        raise ValueError(
            "cache_key needs an engine_commit: without it the key cannot say WHICH "
            "code produced the record, which is the half of §10's key that makes a hit "
            "sound. The store is disabled in that case rather than keyed on the config "
            "alone."
        )
    return f"{config.config_hash()}-{engine_commit[:12]}"


@dataclass
class RecordStore:
    """The shared, content-addressed store of run records (§10.2).

    One store across every sweep, because §14(a)'s calibration sweeps overlap almost
    entirely and a cell computed for one is the same measurement for the next.  Each
    entry is BOTH halves of ``artifact.write_artifact``'s output — see the module
    docstring for why the CSV is stored rather than re-rendered.

    **TWO DIFFERENT REASONS NOT TO USE THE CACHE, AND THEY ARE NOT THE SAME REFUSAL.**
    Collapsing them was the first draft's bug, caught before the tests:

    * ``--no-cache`` says *recompute*, not *distrust the sha*.  The key is still sound,
      so the fresh record is written to the SHARED store, refreshing it.
    * a DIRTY or UNKNOWN tree says the sha no longer identifies the code, so neither a
      read nor a write is sound: a record written from uncommitted work is
      indistinguishable from one written at that commit, and writing it to the shared
      store would serve it to a later CLEAN run.  Those records go to the sweep's own
      ``records/`` directory instead, so the sweep still produces its frame while the
      shared store stays trustworthy.

    Either way ``disabled_reason`` is recorded rather than left to be inferred from a
    hit count of zero.
    """

    root: Path
    #: May a hit be served from this store at all?
    readable: bool = True
    #: Is this the shared store, or a sweep-local fallback for an untrustworthy sha?
    shared: bool = True
    disabled_reason: "str | None" = None
    hits: int = 0
    misses: int = 0

    @classmethod
    def open(cls, root: "str | Path", *, engine_commit: "str | None",
             engine_dirty: bool, use_cache: bool = True,
             fallback_root: "str | Path | None" = None) -> "RecordStore":
        if engine_commit is None:
            reason = MANIFEST_WARNING_CODES["engine_unknown"]
        elif engine_dirty:
            reason = MANIFEST_WARNING_CODES["engine_dirty"]
        else:
            return cls(root=Path(root), readable=use_cache, shared=True,
                       disabled_reason=None if use_cache
                       else "disabled by the caller (--no-cache); fresh records still "
                            "refresh the shared store, because the engine sha is sound")
        return cls(
            root=Path(root if fallback_root is None else fallback_root),
            readable=False,
            shared=False,
            disabled_reason=reason + " — records for this sweep are written beside its "
                                     "manifest rather than into the shared store",
        )

    def json_path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def csv_path(self, key: str) -> Path:
        return self.root / f"{key}.csv"

    def has(self, key: str) -> bool:
        """A hit needs BOTH halves — a JSON without its CSV is a half-written entry,
        and serving it would leave the sweep frame short one cell with no error."""
        if not self.readable:
            return False
        return (self.json_path(key).exists() and self.json_path(key).stat().st_size > 0
                and self.csv_path(key).exists() and self.csv_path(key).stat().st_size > 0)

    def put(self, key: str, report: "EvalReport") -> dict[str, Path]:
        """Write a computed cell's two halves into whichever root this store opened on."""
        self.root.mkdir(parents=True, exist_ok=True)
        return {
            "json": artifact_module.write_json(report, self.json_path(key)),
            "csv": artifact_module.write_csv(report, self.csv_path(key)),
        }

    def csv_lines(self, key: str) -> list[str]:
        text = self.csv_path(key).read_text(encoding="utf-8")
        return [line for line in text.split("\n") if line]

    def record_summary(self, key: str) -> dict[str, Any]:
        """The few record fields a CELL quotes — read from the JSON, not recomputed.

        Quoting them per cell is what makes a mixed-version sweep DETECTABLE: a record
        written under a 28-declaration registry and one written under 31 are both valid
        and not comparable, and the manifest is where that becomes visible (§10.2).
        """
        data = json.loads(self.json_path(key).read_text(encoding="utf-8"))
        provenance = data.get("provenance") or {}
        return {
            "schema_version": data.get("schema_version"),
            "run_id": data.get("run_id"),
            "day_tier": provenance.get("day_tier"),
            "engine_commit": provenance.get("engine_commit"),
        }


def registry_fingerprint(registry: MetricRegistry = METRICS) -> str:
    """A short hash over the registry's DECLARATIONS (§5.1), for the manifest.

    Declarations, not rows — the same unit the periodic metric-set review counts, and
    the same call s52 made and the user confirmed ("count DECLARATIONS, not rows").  The
    flat cell count rides along because a breakdown gaining a key changes what a frame
    contains without changing any declaration's name.
    """
    payload = json.dumps(
        {
            "scalars": sorted(d.name for d in registry.scalars()),
            "breakdowns": sorted(b.name for b in registry.breakdowns),
            "distributions": sorted(d.name for d in registry.distributions()),
            "cells": len(registry),
        },
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def sweep_hash(cells: "Iterable[SweepCell]") -> str:
    """Identity over WHICH MEASUREMENTS the sweep asks for — and not over the engine.

    **Identity excludes the engine; validity includes it** (§10.1).  The precedent is in
    the codebase: ``artifact.run_id`` leaves the commit out because "folding it in would
    make the id churn on every commit for runs that are otherwise the same scenario".  A
    sweep re-run at a new engine version is the same study, so it keeps its id and its
    directory while every record in it is re-derived under a new cache key.
    """
    payload = json.dumps([c.config.canonical() for c in cells],
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Running a sweep
# ---------------------------------------------------------------------------

@dataclass
class SweepResult:
    """What one invocation produced: the manifest dict and where it was written."""

    declaration: SweepDeclaration
    sweep_id: str
    directory: Path
    manifest: dict[str, Any]
    manifest_path: "Path | None" = None
    frame_path: "Path | None" = None
    store: "RecordStore | None" = None

    @property
    def cells(self) -> list[dict[str, Any]]:
        return self.manifest["cells"]

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [c for c in self.cells if c["status"] == CELL_FAILED]

    @property
    def warning_codes(self) -> list[str]:
        return [w["code"] for w in self.manifest["warnings"]]


DEFAULT_STORE = Path("artifacts/records")
DEFAULT_SWEEP_ROOT = Path("artifacts/sweeps")


def sweep_id(declaration: SweepDeclaration, cells: "Sequence[SweepCell]") -> str:
    return f"{declaration.name}-{sweep_hash(cells)}"


def run_sweep(declaration: SweepDeclaration, *,
              store_root: "str | Path" = DEFAULT_STORE,
              sweep_root: "str | Path" = DEFAULT_SWEEP_ROOT,
              use_cache: bool = True,
              registry: MetricRegistry = METRICS,
              write: bool = True,
              on_cell: "Callable[[int, SweepCell, dict[str, Any]], None] | None" = None,
              ) -> SweepResult:
    """Run every cell of ``declaration``, caching by §10's key, and write the manifest.

    Cells run in declaration-product order.  That order does not affect any NUMBER —
    each cell's ``RunConfig`` carries its own seed and ``simulate`` builds a fresh
    ``SeededRNG`` from it — but it is fixed anyway so a sweep's console output and its
    manifest read the same way twice.
    """
    from .report import engine_version
    from .runner import run as run_one

    engine_commit, engine_dirty = engine_version()
    cells = declaration.cells()
    identifier = sweep_id(declaration, cells)
    directory = Path(sweep_root) / identifier
    # The fallback root is why the cells are resolved BEFORE the store is opened: an
    # untrustworthy sha sends records beside this sweep's manifest instead of into the
    # shared store, and that path is not known until the sweep has its id.
    store = RecordStore.open(store_root, engine_commit=engine_commit,
                             engine_dirty=engine_dirty, use_cache=use_cache,
                             fallback_root=directory / "records")

    rows: list[dict[str, Any]] = []
    frame: list[str] = []
    headers: dict[str, list[str]] = {}

    for index, cell in enumerate(cells):
        row: dict[str, Any] = {
            "coordinate": dict(cell.coordinate),
            "run_id": None,
            "config_hash": cell.config.config_hash(),
            "cache_key": None,
            "record": None,
            "source": None,
            "status": CELL_OK,
            "day_tier": cell.config.day_tier,
            #: Carried per cell because the `precision` warning keys on the DAY COUNT
            #: rather than the tier NAME — see `_manifest_warnings`.
            "n_days": cell.config.n_days,
            "schema_version": None,
            "engine_commit": engine_commit,
            "note": None,
        }
        key: "str | None" = None
        try:
            if engine_commit is not None:
                key = cache_key(cell.config, engine_commit)
            if key is not None and store.has(key):
                store.hits += 1
                row["source"] = SOURCE_CACHED
            else:
                report = run_one(cell.config, registry=registry)
                if key is None:
                    # No engine sha: the record still has to go SOMEWHERE, and the
                    # config hash alone is the honest key — it says which scenario,
                    # and the manifest's engine_unknown warning says the rest.
                    key = f"{cell.config.config_hash()}-unknown"
                store.put(key, report)
                store.misses += 1
                row["source"] = SOURCE_COMPUTED
            row["cache_key"] = key
            row.update(store.record_summary(key))
            row["record"] = _relative(store.json_path(key), directory)
            lines = store.csv_lines(key)
            headers.setdefault(lines[0], []).append(_coordinate_label(cell.coordinate))
            if not frame:
                frame.append(lines[0])
            frame.extend(lines[1:])
        except Exception as exc:                     # noqa: BLE001 - recorded, not swallowed
            row["status"] = CELL_FAILED
            row["note"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        if on_cell is not None:
            on_cell(index, cell, row)

    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "name": declaration.name,
        "sweep_id": identifier,
        "sweep_hash": sweep_hash(cells),
        "declaration": declaration.to_dict(),
        "engine_commit": engine_commit,
        "engine_dirty": engine_dirty,
        "generated_at": _now(),
        "axes": list(declaration.axes),
        "n_cells": len(cells),
        "record_schema_version": artifact_module.SCHEMA_VERSION,
        "registry_fingerprint": registry_fingerprint(registry),
        "cells": rows,
        "cache": {
            "store": str(store.root),
            "shared": store.shared,
            "hits": store.hits,
            "misses": store.misses,
            "disabled_reason": store.disabled_reason,
        },
        "warnings": _manifest_warnings(rows, headers, engine_commit=engine_commit,
                                       engine_dirty=engine_dirty),
    }

    result = SweepResult(declaration=declaration, sweep_id=identifier,
                         directory=directory, manifest=manifest, store=store)
    if write:
        directory.mkdir(parents=True, exist_ok=True)
        result.manifest_path = directory / "manifest.json"
        result.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                                        encoding="utf-8")
        # §10.2: heterogeneous cells are REFUSED, not concatenated.  The manifest is
        # still written — it is what names the cells that differ — but a frame whose
        # columns meant different things in different blocks would not be tidy, it
        # would be two frames stacked, and nothing downstream could tell.
        if frame and len(headers) <= 1:
            result.frame_path = directory / f"{declaration.name}.csv"
            result.frame_path.write_text("\n".join(frame) + "\n", encoding="utf-8")
    return result


def _manifest_warnings(rows: list[dict[str, Any]], headers: dict[str, list[str]], *,
                       engine_commit: "str | None", engine_dirty: bool,
                       ) -> list[dict[str, str]]:
    """Top-level warnings over the closed :data:`MANIFEST_WARNING_CODES` vocabulary.

    Top level for §9.1's reason: a reader who has to open a nested block to discover
    that a result is not comparable will not open it.
    """
    warnings: list[dict[str, str]] = []
    if engine_commit is None:
        warnings.append({"code": "engine_unknown",
                         "message": MANIFEST_WARNING_CODES["engine_unknown"]})
    elif engine_dirty:
        warnings.append({"code": "engine_dirty",
                         "message": MANIFEST_WARNING_CODES["engine_dirty"]})

    # §9.1 raises the RECORD's `precision` warning on `day_tier == "quick"`.  A sweep
    # cannot key on the tier NAME, because "custom" has no position in that vocabulary
    # and spans both sides of quick: a sweep over `n_days: [2000, 20000]` has one cell
    # at "quick" and one at "custom" that is TEN TIMES better, while a 60-day cell is
    # also "custom" and is far worse.  Found by eye on a 60-day smoke sweep, which the
    # name-keyed first draft passed silently.  So the manifest keys on the DAY COUNT,
    # which is ordered: quick or below.
    imprecise = [r for r in rows if _cell_days(r) is not None
                 and _cell_days(r) <= DAY_TIERS["quick"]]
    if imprecise:
        warnings.append({
            "code": "precision",
            "message": (f"{len(imprecise)} of {len(rows)} cell(s) ran at or below the "
                        f"'quick' tier ({DAY_TIERS['quick']:,} days): iteration runs, "
                        f"not publishable ones. Smallest: "
                        f"{min(_cell_days(r) for r in imprecise):,} days."),
        })

    # The heterogeneity check §10.2 asks for.  `write_sweep_csv` already raises when
    # two reports' columns differ; s57 promotes that from an incidental column error
    # into a manifest check that NAMES the cells which differ, because by then
    # schema_version and registry_fingerprint are already in every cell.
    if len(headers) > 1:
        groups = "; ".join(
            f"{len(labels)} cell(s) incl. {labels[0]}" for labels in headers.values()
        )
        warnings.append({
            "code": "heterogeneous_records",
            "message": (f"{len(headers)} different tidy-CSV headers across the sweep "
                        f"({groups}). The cells were produced under different metric "
                        "registries or record schema versions and must not be pooled "
                        "into one frame."),
        })
    versions = {r["schema_version"] for r in rows if r["status"] == CELL_OK}
    if len(versions) > 1 and len(headers) <= 1:      # pragma: no cover - defensive
        warnings.append({
            "code": "heterogeneous_records",
            "message": f"cells carry record schema_version {sorted(versions)}.",
        })

    failed = [_label(r) for r in rows if r["status"] == CELL_FAILED]
    if failed:
        shown = ", ".join(failed[:3])
        more = f" (+{len(failed) - 3} more)" if len(failed) > 3 else ""
        warnings.append({
            "code": "cells_failed",
            "message": (f"{len(failed)} of {len(rows)} cell(s) produced no record: "
                        f"{shown}{more}. The manifest is written anyway so the other "
                        "results are not lost; the CLI exits non-zero."),
        })
    return warnings


def _cell_days(row: dict[str, Any]) -> "int | None":
    """A cell's ``n_days``, read off the coordinate or the declaration's base.

    The manifest does not repeat every resolved config field per cell — the record does
    that — so this reads the one field the ``precision`` check needs.
    """
    return row.get("n_days")


def _label(row: dict[str, Any]) -> str:
    return _coordinate_label(row["coordinate"])


def _coordinate_label(coordinate: dict[str, Any]) -> str:
    return "{" + ", ".join(f"{k}={v}" for k, v in coordinate.items()) + "}"


def _repo_relative(path: "Path | None") -> "str | None":
    """A declaration's path as the manifest records it: relative to the repo root.

    Found by rendering one real output by eye (ritual step 6).  The first draft wrote
    ``str(self.source_path)``, which put an ABSOLUTE path to somebody's scratchpad into
    an artifact whose whole purpose is to be committed and read later: machine-specific,
    unresolvable for any other reader, and in the one field that says where the study
    was declared.  ``engine_commit`` plus a repo-relative path identifies the
    declaration exactly; an absolute path identifies it for one person on one machine.
    """
    if path is None:
        return None
    root = Path(__file__).resolve().parents[2]
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        # Outside the repo (an ad-hoc declaration in a scratch directory). The name is
        # all that can be said honestly — the rest would not resolve for anyone else.
        return resolved.name


def _relative(path: Path, start: Path) -> str:
    """``path`` as seen from the manifest's own directory, POSIX-style.

    Relative so a sweep directory can be moved or served as static content without
    every record pointer breaking — the §9 line that the sim never knows about the site.
    """
    import os.path

    return Path(os.path.relpath(path.resolve(), start.resolve())).as_posix()


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _plan_text(declaration: SweepDeclaration, cells: "Sequence[SweepCell]") -> str:
    lines = [
        f"sweep: {declaration.name}  ({len(cells)} cells)",
        f"  axes: {', '.join(f'{k}={v}' for k, v in declaration.axes.items())}",
    ]
    if declaration.description:
        lines.insert(1, f"  {declaration.description.strip()}")
    total_days = sum(c.config.n_days for c in cells)
    lines.append(f"  total days: {total_days:,}")
    lines.append("")
    width = max((len(_coordinate_label(c.coordinate)) for c in cells), default=0)
    for cell in cells:
        lines.append(f"  {_coordinate_label(cell.coordinate):<{width}}  "
                     f"{cell.config.n_days:>8,}d  {cell.config.config_hash()}")
    return "\n".join(lines)


def main(argv: "Sequence[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m src.evaluation.sweep",
        description="Run a declared sweep (evaluation_framework.md §10).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("plan", "resolve and print the cells; simulate nothing"),
                            ("run", "run every cell, caching by §10's key")):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("declaration", help="path to a sweeps/*.yaml declaration")
        if name == "run":
            child.add_argument("--store", default=str(DEFAULT_STORE),
                               help=f"record store (default: {DEFAULT_STORE})")
            child.add_argument("--out", default=str(DEFAULT_SWEEP_ROOT),
                               help=f"sweep output root (default: {DEFAULT_SWEEP_ROOT})")
            child.add_argument("--no-cache", action="store_true",
                               help="recompute every cell, ignoring the store")

    args = parser.parse_args(argv)
    declaration = SweepDeclaration.load(args.declaration)

    if args.command == "plan":
        print(_plan_text(declaration, declaration.cells()))
        return 0

    def report_cell(index: int, cell: SweepCell, row: dict[str, Any]) -> None:
        mark = {SOURCE_CACHED: "cached", SOURCE_COMPUTED: "ran"}.get(row["source"], "")
        suffix = f"  [{mark}]" if mark else f"  [FAILED: {row['note']}]"
        print(f"  [{index + 1}/{total}] {_coordinate_label(cell.coordinate)}{suffix}",
              flush=True)

    cells = declaration.cells()
    total = len(cells)
    print(_plan_text(declaration, cells))
    print()
    result = run_sweep(declaration, store_root=args.store, sweep_root=args.out,
                       use_cache=not args.no_cache, on_cell=report_cell)
    print()
    print(f"manifest: {result.manifest_path}")
    if result.frame_path is not None:
        print(f"frame:    {result.frame_path}")
    cache = result.manifest["cache"]
    if cache["disabled_reason"]:
        # "0 hit(s), 16 miss(es)" reads as sixteen keys that failed to match, when in
        # fact the cache was never consulted — two different facts, and the second is
        # the one a reader needs.  Ritual step 6's class of defect exactly: the numbers
        # were right and the sentence presenting them was not.
        print(f"cache:    DISABLED — {cache['disabled_reason']}")
        print(f"          {cache['misses']} cell(s) computed into {cache['store']}")
    else:
        print(f"cache:    {cache['hits']} hit(s), {cache['misses']} miss(es)")
    for warning in result.manifest["warnings"]:
        print(f"WARNING [{warning['code']}] {warning['message']}")
    return 1 if result.failed else 0


if __name__ == "__main__":                           # pragma: no cover
    raise SystemExit(main())
