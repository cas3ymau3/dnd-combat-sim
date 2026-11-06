"""
console.py — the third renderer (§9): an :class:`EvalReport` as readable text.

§9 calls the console table *"a third renderer, not a special case"*, and that phrasing
is the design.  It reads the same :class:`~src.evaluation.report.EvalReport` and the
same row shape :mod:`~src.evaluation.artifact` serializes, so a number shown here and a
number in the JSON are one computation rendered twice.  Nothing in this file computes a
statistic, and nothing in it sums anything.

Three rules this renderer exists to obey
----------------------------------------
**It never fabricates a total.**  Margins are computed in the estimating layer because N
correlated cell estimates cannot be combined downstream (§5.4).  A renderer that adds a
column up would be inventing a standard error it has no covariance for — and for a
breakdown whose cells OVERLAP it would also be double-counting.  So the cells and the
declared margin are printed as separate blocks, and an overlapping breakdown prints an
explicit do-not-sum line — in one of two wordings, because overlap has two causes: an
UNCROSSED breakdown reports each dimension independently (every cell covers the whole
quantity), while a CROSSED one can overlap because its keys are not disjoint (a crit is
also a hit).  Telling a reader the wrong one of those is telling them something false
about the shape of the data.

**It shows the three states as three states** (§3.4).  Unavailable and unmeasured rows
are printed with their reason, in their own section, never as ``0.00``.

**It puts the warnings where they will be read** — at the end, unindented, after the
numbers, because that is where a reader's eye stops.

The RENDERED text is ASCII wherever this file writes it (``+/-``, not ``±``), because
this goes to a Windows console where cp1252 turns one stray character into a
``UnicodeEncodeError`` that takes the whole run's output with it.  What this file cannot
make ASCII is the text it QUOTES: the registry's availability reasons and the epistemic
note cite design sections with a section sign.  :func:`print_report` therefore degrades
those characters rather than letting a footnote kill the numbers.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, TextIO

from .artifact import (
    STATUS_MEASURED,
    SUM_RULE_OVERLAP,
    report_to_dict,
    run_id,
)
from .enemy import ENEMY_OPTION_SCHEMA

if TYPE_CHECKING:                                    # pragma: no cover
    from .report import EvalReport

_RULE = "=" * 78
_THIN = "-" * 78


def _fmt_value(row: dict[str, Any]) -> str:
    """One estimate as ``value +/- stderr``, or the reason it is not one."""
    if row["status"] != STATUS_MEASURED:
        return row["status"].upper()
    value, stderr = row["value"], row["stderr"]
    text = f"{value:>12,.4g}"
    if stderr is not None:
        text += f" +/- {stderr:<9.3g}"
    else:
        text += " " * 14
    return text


def _fmt_days(days: float) -> str:
    """A day count a reader can compare against §10's tiers at a glance."""
    if days >= 1_000_000:
        return f"{days / 1_000_000:.2g}M"
    if days >= 10_000:
        return f"{round(days / 1_000):,.0f}k"
    return f"{round(days):,.0f}"


def _flag(row: dict[str, Any]) -> str:
    """A trailing marker for a row a reader should not take at face value.

    **The bare `[unconverged]` was the same word for two opposite situations
    (§14(a), fixed s56).**  At band 5-10, 58% of the #6a run's flags cleared with at
    most double the days — `saves_forced_per_round[dex_save|*]` at L10 needed FIFTY-
    EIGHT more — while six needed over a hundred times the tier, one of them twice
    the publication budget because the channel barely exists at that CR.  A reader
    could not tell those apart, and no constant fixes that, so the flag now carries
    the binding criterion's own two numbers and the days it would take.

    Three shapes, and the third is the one that matters:

        [unconverged: rel_stderr 0.043 vs 0.02, ~9.2k days (4.6x)]
        [unconverged: min_days 40 vs 100, ~100 days (2.5x)]
        [unconverged: ci_width_vs_spread 0.667 vs 0.1, no day count helps]

    "no day count helps" is NOT "a very large number of days".  It is printed only
    where the criterion has no known scaling in n (a distribution's interval width)
    or where no n satisfies it at all (a ratio-scale estimate sitting exactly on
    zero), and the row's `convergence.note` says which.  Units are deliberately
    left to the criterion NAME rather than formatted per criterion: `rel_stderr` is
    a fraction, `resolution_sigmas` is standard errors, the two floors are counts,
    and a renderer that guessed would be a fourth place that has to be kept in step.
    """
    if row["status"] != STATUS_MEASURED or row["converged"]:
        return ""
    verdict = row["convergence"]
    criterion = verdict["criterion"]
    if criterion is None:                     # defensive: unconverged names one
        return "  [unconverged]"
    attained, required = verdict["attained"], verdict["required"]
    parts = [criterion if attained is None or required is None
             else f"{criterion} {attained:.3g} vs {required:.3g}"]
    days, factor = verdict["days_required"], verdict["days_factor"]
    if days is None:
        parts.append("no day count helps")
    else:
        parts.append(f"~{_fmt_days(days)} days"
                     + (f" ({factor:.3g}x)" if factor is not None else ""))
    return "  [unconverged: " + ", ".join(parts) + "]"


#: Floor for the metric-name column.  The width is DERIVED from the rows being
#: rendered rather than fixed, because a fixed one goes stale silently: s51
#: registered `control_turns_reduced_applied_per_round` (39 characters) against a
#: hardcoded 34, and every row longer than the column pushed its own value column
#: right — caught by the per-feature ritual's "render one real output by eye", which
#: is the fifth session running it has found something.
_NAME_FLOOR = 34


def _name_width(rows: "list[dict[str, Any]]") -> int:
    """The metric-name column width for one block of scalar rows."""
    return max([_NAME_FLOOR] + [len(r["metric"]) + 2 for r in rows])


def _scalar_line(row: dict[str, Any], *, indent: str = "  ",
                 width: int = _NAME_FLOOR) -> str:
    return (f"{indent}{row['metric']:<{width}}{_fmt_value(row)}"
            f"  per {row['denominator']}{_flag(row)}")


def _cell_line(row: dict[str, Any], dimensions: list[str]) -> str:
    key = row["key"] or {}
    label = " | ".join(str(key.get(d, "")) for d in dimensions)
    return f"    {label:<32}{_fmt_value(row)}{_flag(row)}"


def _dist_line(row: dict[str, Any]) -> str:
    """One distribution point: ``value  [lo, hi]``, never ``value +/- half-width``.

    A quantile's interval is asymmetric, so printing a +/- would be a lie about the
    estimator even if the number beside it were right.  Printing the bracket is also
    what makes the ABSENCE of one legible: a point whose interval could not be placed
    shows the estimate and ``(no interval)``, not a tighter-looking bare number.
    """
    label = (row["key"] or {}).get("statistic", "?")
    if row["status"] != STATUS_MEASURED:
        return f"    {label:<10}{row['status'].upper()}"
    ci = row["ci95"]
    interval = (f"[{ci[0]:,.4g}, {ci[1]:,.4g}]" if ci
                else "(no interval -- sample too small to place one)")
    return (f"    {label:<10}{row['value']:>12,.4g}  {interval:<30}"
            f"{row['method']}{_flag(row)}")


def _enemy_line(provenance: Any) -> str:
    """The header's one-line summary of WHICH enemy this run faced (§3.4 / §4).

    Added s50, and the gap it closes is the s49 defect pattern repeating: the enemy
    block is the whole deliverable of the §13 step-5 seam, the JSON artifact carried
    it from the first commit, and the console — one of the three renderers, and the
    one a person actually reads — mentioned the enemy exactly ONCE, inside a
    comparability warning paragraph.  §4 calls the provenance block "the source for
    the model-description / baseline-assumptions page", which a reader cannot use if
    the renderer drops it.

    Non-default options only.  Printing all nine at their defaults would bury the
    one or two that are in force, which is the 400-character margin-note mistake s49
    fixed on the line below this one.
    """
    block = provenance.resolved.get("enemy") or {}
    path = provenance.coverage.get("enemy_path", "unknown")
    # The "NOT RESOLVED" branch this carried through s50-s51 is gone with the baked-in
    # path (s52): every run's enemy is built by the seam, so there is no longer a case
    # where the console has to tell a reader the assumptions were not recorded.
    defaults = {name: spec.default
                for name, spec in ENEMY_OPTION_SCHEMA.items()}
    active = [f"{name}={value!r}" for name, value in sorted(block["options"].items())
              if value != defaults.get(name)]
    suffix = f"  [{', '.join(active)}]" if active else "  [all options at default]"
    return f"{path}  level {block['level']} band {block['band']}{suffix}"


def _coord_value(value: Any) -> str:
    """A coordinate position for display: a declared BAND reads as ``11-16``.

    A ``contains`` dimension's value is a two-element range, and rendering it as a
    Python list (``[11, 16]``) puts punctuation in front of the reader for no gain.
    """
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]}-{value[1]}"
    return str(value)


def _score_lines(block: dict[str, Any]) -> list[str]:
    """The §11.2 ``scores`` section, rendered.

    **This exists so the block is not a writer with no reader.**  s53 found a telemetry
    channel dead at both ends and s56 found a §4 provenance requirement satisfied in
    code nothing serialized; both are the same defect, and shipping a scores section no
    renderer reads would be the third instance in three sessions.  So the console reads
    it, and the roll call names this as the reader.

    Two things it must not do.  It must not print a DELTA for an interval baseline (the
    distance to a band is not a number the band supports), and it must not let an
    ``external_published`` score read as a shortfall — §11's correction is that such a
    figure is a REFERENCE POINT, so its warning is printed beside the number rather than
    filed away in the JSON.
    """
    out: list[str] = []
    rows = block["scores"]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    out.append("")
    out.append(f"BASELINE SCORES  ({len(rows)}) -- "
               + ", ".join(f"{n} {state}" for state, n in sorted(counts.items())))
    out.append(_THIN)
    out.append(f"  baseline set {block['baselines_fingerprint']}"
               f"   (schema {block['baselines_schema_version']})")
    # A warning that holds for EVERY score of a source is a fact about the source, so
    # it is printed once there rather than on each row.  Found by rendering this by eye:
    # the first draft printed 'reference_point' and 'basis_unknown' on all four damage
    # classes -- two facts, eight lines, burying the four verdicts that are the answer.
    hoisted: dict[str, set[str]] = {}
    for src in block["sources"]:
        mine = [r for r in rows if r["source"] == src["name"]]
        sets = [{w["code"] for w in r["warnings"]} for r in mine]
        hoisted[src["name"]] = set.intersection(*sets) if sets else set()
        marker = "  REFERENCE POINT, not a target" if src["is_reference_point"] else ""
        out.append(f"  [{src['kind']}] {src['name']}"
                   f"   {src['n_entries']} entr{'y' if src['n_entries'] == 1 else 'ies'}"
                   f"{marker}")
        for code in sorted(hoisted[src["name"]]):
            message = next(w["message"] for r in mine for w in r["warnings"]
                           if w["code"] == code)
            out.append(f"      [{code}] {message}   (all {len(mine)} score(s))")
    for row in rows:
        label = row["coordinate"] or {}
        coord = " ".join(f"{k}={_coord_value(label[k])}" for k in sorted(label))
        head = f"  {row['metric']}  vs {row['source']}"
        if coord:
            head += f" [{coord}]"
        if row["state"] != "scored":
            out.append(f"{head}   {row['state'].upper()}")
            if row["note"]:
                out.append(f"      {row['note']}")
            continue
        if row["baseline_interval"] is not None:
            band = row["baseline_interval"]
            # Interval notation, because the CLOSURE is load-bearing: a band whose
            # lower bound is exclusive at the same number where the one below it is
            # inclusive is how the scale partitions (§11.1), and printing bare numbers
            # would hide it. The source's own listing rides alongside.
            published = (f"  (published {band['published']})"
                         if band.get("published") else "")
            out.append(f"{head}   {row['value']:,.4g} vs {band['label']}"
                       f"   -> {row['verdict'].upper()}{published}")
        else:
            ratio = ("n/a" if row["ratio"] is None else f"{row['ratio']:,.3f}x")
            out.append(f"{head}   {row['value']:,.4g} vs {row['baseline']:,.4g}"
                       f"   delta {row['delta']:+,.4g}   ratio {ratio}")
        for warning in row["warnings"]:
            if warning["code"] in hoisted.get(row["source"], ()):
                continue
            out.append(f"      [{warning['code']}] {warning['message']}")
    return out


def render(report: "EvalReport", *, baselines: "Any | None" = None) -> str:
    """The whole report as one text block.

    ``baselines`` (§11.2) adds the BASELINE SCORES section; without one the output is
    byte-identical to what it has always been, so no existing rendered artifact moves.
    """
    record = report_to_dict(report, include_data_dictionary=False,
                            baselines=baselines)
    provenance = report.provenance
    config = provenance.config
    results = record["results"]
    out: list[str] = []

    # -- header ---------------------------------------------------------
    commit = provenance.engine_commit or "unknown"
    out.append(_RULE)
    out.append(f"{run_id(report)}   ({config['build']} level {config['level']})")
    out.append(
        f"  {config['n_days']:,} days ({provenance.day_tier})"
        f"   mode={config['mode']}   attribution={config['attribution']}"
    )
    out.append(f"  engine {commit[:12]}"
               + ("  *** DIRTY TREE ***" if provenance.engine_dirty else "")
               + (f"   paired seed {provenance.pairing['seed']}"
                  if provenance.pairing else ""))
    roster = ", ".join(f"{role}: {', '.join(names)}"
                       for role, names in provenance.roster.items() if names)
    if roster:
        out.append(f"  roster  {roster}")
    out.append(f"  enemy   {_enemy_line(provenance)}")
    out.append(_RULE)

    # -- headline (§5.3: exactly one, and it is a scalar) ----------------
    headline_name = results["headline"]
    headline = next(r for r in results["scalars"] if r["metric"] == headline_name)
    out.append("")
    out.append(f"HEADLINE   {headline['metric']}   {_fmt_value(headline).strip()}"
               f"   per {headline['denominator']}")
    ci = headline["ci95"]
    if ci:
        out.append(f"           95% CI  [{ci[0]:,.4g}, {ci[1]:,.4g}]"
                   f"   n = {headline['n']:,} days")
    out.append("           (one declared quantity; no composite build score)")

    # -- scalar groups --------------------------------------------------
    for group, title in (("panel", "PANEL"), ("column", "COLUMNS")):
        rows = [r for r in results["scalars"]
                if r["group"] == group and r["status"] == STATUS_MEASURED]
        if not rows:
            continue
        out.append("")
        out.append(title)
        out.append(_THIN)
        width = _name_width(rows)
        out.extend(_scalar_line(r, width=width) for r in rows)

    # -- breakdowns (§5.4) ----------------------------------------------
    blocks = [b for b in results["breakdowns"]
              if any(r["status"] == STATUS_MEASURED for r in b["cells"] + b["margins"])]
    if blocks:
        out.append("")
        out.append("BREAKDOWNS")
        out.append(_THIN)
    for block in blocks:
        dimensions = block["dimensions"]
        out.append("")
        out.append(f"  {block['name']}  [{' x '.join(dimensions)}]"
                   f"  unit={block['unit']}")
        if block["sum_rule"] == SUM_RULE_OVERLAP:
            # Overlap has TWO causes and they are not the same warning (s49).  An
            # UNCROSSED breakdown reports each dimension independently, so every
            # cell covers the whole quantity.  A CROSSED one can still overlap
            # because its KEYS are not disjoint -- attack_roll_rate's crit cell is a
            # subset of its hit cell.  Printing "reported INDEPENDENTLY" over the
            # second case tells a reader something false about the shape of the
            # data, which is how this was caught: by reading one real report.
            out.append("    (dimensions reported INDEPENDENTLY -- cells overlap; "
                       "do NOT sum them)"
                       if not block["crossed"] else
                       "    (cells are NOT disjoint -- one event can satisfy "
                       "several; do NOT sum them)")
        cells = [r for r in block["cells"] if r["status"] == STATUS_MEASURED]
        out.extend(_cell_line(r, dimensions) for r in cells)
        margins = [r for r in block["margins"] if r["status"] == STATUS_MEASURED]
        if margins:
            # The reason a margin is estimated here differs by kind, and saying the
            # wrong one is worse than saying nothing.  For a CROSSED breakdown the
            # margin does equal the sum in VALUE -- what a consumer cannot rebuild is
            # its standard error, which needs the cells' covariance.  For an UNCROSSED
            # one the cells overlap, so the sum is not even the right number.
            out.append("    -- declared margins ("
                       + ("NOT a sum: the cells above overlap"
                          if block["sum_rule"] == SUM_RULE_OVERLAP
                          else "estimated here: the stderr is not reconstructible "
                               "from the cells")
                       + ") --")
            out.extend(_cell_line(r, dimensions) for r in margins)
        elif block["margin_note"]:
            out.append(f"    (no margin declared: {block['margin_note']})")

    # -- distributions (§5.4 kind 3) -------------------------------------
    shapes = [b for b in results["distributions"]
              if any(r["status"] == STATUS_MEASURED for r in b["points"])]
    if shapes:
        out.append("")
        out.append("DISTRIBUTIONS   (the SHAPE of a per-day quantity, not its average)")
        out.append(_THIN)
    for block in shapes:
        out.append("")
        out.append(f"  {block['name']}  over {block['over']}"
                   f"  unit={block['unit']}")
        out.append("    (intervals are ASYMMETRIC and are not value +/- stderr; "
                   "a quantile has none)")
        out.extend(_dist_line(r) for r in block["points"]
                   if r["status"] == STATUS_MEASURED)

    # -- the two non-measured states, kept apart (§3.4) ------------------
    every = list(results["scalars"])
    for block in results["breakdowns"]:
        every.extend(block["cells"] + block["margins"])
    for block in results["distributions"]:
        every.extend(block["points"])
    for status, title, blurb in (
        ("unavailable", "UNAVAILABLE",
         "this run structurally cannot produce these -- NOT a measured zero"),
        ("unmeasured", "UNMEASURED",
         "available, but this run's denominator was zero"),
    ):
        rows = [r for r in every if r["status"] == status]
        if not rows:
            continue
        out.append("")
        out.append(f"{title}  ({len(rows)}) -- {blurb}")
        out.append(_THIN)
        reasons: dict[str, list[str]] = {}
        for row in rows:
            reasons.setdefault(row["note"] or "(no reason recorded)", []).append(
                row["metric"])
        for reason, names in reasons.items():
            shown = ", ".join(sorted(names)[:6])
            more = f" (+{len(names) - 6} more)" if len(names) > 6 else ""
            out.append(f"  {shown}{more}")
            out.append(f"      {reason}")

    # -- baseline scores (§11.2), before the warnings ------------------
    if "scores" in record:
        out.extend(_score_lines(record["scores"]))

    # -- warnings, last, where the eye stops ----------------------------
    out.append("")
    out.append("WARNINGS")
    out.append(_THIN)
    for warning in record["warnings"]:
        out.append(f"  [{warning['code']}] {warning['message']}")

    out.append("")
    out.append("EPISTEMIC NOTE")
    out.append(_THIN)
    out.append(f"  {provenance.epistemic_note}")
    out.append(_RULE)
    return "\n".join(out)


def print_report(report: "EvalReport", file: "TextIO | None" = None, *,
                 baselines: "Any | None" = None) -> None:
    """Print the report, degrading gracefully on a narrow console encoding.

    This file's own scaffolding is ASCII, but the text it renders is not entirely:
    the registry's availability reasons and the epistemic note cite design sections
    with a section sign.  On a cp1252 Windows console that raises, and losing a whole
    run's output to one character in a footnote is a bad trade -- so unrepresentable
    characters are replaced and the numbers still arrive.
    """
    stream = file or sys.stdout
    text = render(report, baselines=baselines)
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding), file=stream)
