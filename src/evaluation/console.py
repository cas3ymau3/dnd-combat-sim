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
column up would be inventing a standard error it has no covariance for — and for an
UNCROSSED breakdown it would also be double-counting, since each dimension covers the
whole quantity.  So the cells and the declared margin are printed as separate blocks,
and an uncrossed breakdown prints an explicit do-not-sum line.

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


def _flag(row: dict[str, Any]) -> str:
    """A trailing marker for a row a reader should not take at face value."""
    if row["status"] == STATUS_MEASURED and not row["converged"]:
        return "  [unconverged]"
    return ""


def _scalar_line(row: dict[str, Any], *, indent: str = "  ") -> str:
    return (f"{indent}{row['metric']:<34}{_fmt_value(row)}"
            f"  per {row['denominator']}{_flag(row)}")


def _cell_line(row: dict[str, Any], dimensions: list[str]) -> str:
    key = row["key"] or {}
    label = " | ".join(str(key.get(d, "")) for d in dimensions)
    return f"    {label:<32}{_fmt_value(row)}{_flag(row)}"


def render(report: "EvalReport") -> str:
    """The whole report as one text block."""
    record = report_to_dict(report, include_data_dictionary=False)
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
        out.extend(_scalar_line(r) for r in rows)

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
            out.append("    (dimensions reported INDEPENDENTLY -- cells overlap; "
                       "do NOT sum them)")
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

    # -- the two non-measured states, kept apart (§3.4) ------------------
    every = list(results["scalars"])
    for block in results["breakdowns"]:
        every.extend(block["cells"] + block["margins"])
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


def print_report(report: "EvalReport", file: "TextIO | None" = None) -> None:
    """Print the report, degrading gracefully on a narrow console encoding.

    This file's own scaffolding is ASCII, but the text it renders is not entirely:
    the registry's availability reasons and the epistemic note cite design sections
    with a section sign.  On a cp1252 Windows console that raises, and losing a whole
    run's output to one character in a footnote is a bad trade -- so unrepresentable
    characters are replaced and the numbers still arrive.
    """
    stream = file or sys.stdout
    text = render(report)
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding), file=stream)
