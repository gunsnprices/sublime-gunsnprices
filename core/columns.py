"""Whole-document operations: spec columns for CSV/TSV files and per-line annotations."""
from typing import List, Optional, Tuple

from .extract import Context
from .formats import ALL_COLUMNS, Options, annotation_text, column_value, csv_field
from .titles import looks_like_title, parse_line

COLUMN_PREFIX = "parsed_"
DEFAULT_COLUMNS = ["kind", "brand", "model", "caliber", "capacity", "barrel_in", "rounds", "cost_per_round"]


class ColumnsResult:
    def __init__(self):
        self.suffixes = []      # [(zero-based line, text to append at the end of that line)]
        self.rows = 0           # data rows that got values
        self.empty = 0          # data rows where no gun or ammo title was found (they get empty cells)
        self.error = None       # message when nothing can be done


def add_spec_columns(lines: List[str], ctx: Context, columns: Optional[List[str]] = None,
                     opts: Optional[Options] = None) -> ColumnsResult:
    """Text to append to each line of a CSV/TSV document so that it gets one column per parsed field.

    The header row (if the document has one) gets the column names with the ``parsed_`` prefix. Blank lines are left
    alone. Rows where no gun or ammo title is found get empty cells, so every row keeps the same number of cells.
    """
    res = ColumnsResult()
    opts = opts or Options()
    columns = list(columns or DEFAULT_COLUMNS)
    unknown = [c for c in columns if c not in ALL_COLUMNS]
    if unknown:
        res.error = "Unknown column in the spec_columns setting: %s. Known columns: %s." % (
            ", ".join(unknown), ", ".join(ALL_COLUMNS))
        return res
    if not ctx.delimiter:
        res.error = ("Add Spec Columns works on CSV and TSV files: a .csv/.tsv file, or a file whose first line is a "
                     "header with a title column. Use Parse Titles to CSV for a plain list of titles.")
        return res
    d = ctx.delimiter
    if ctx.header_line is not None and ctx.header_line < len(lines):
        header = lines[ctx.header_line]
        if (COLUMN_PREFIX + columns[0]) in header:
            res.error = "This file already has the %s columns." % (COLUMN_PREFIX + columns[0])
            return res
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        if idx == ctx.header_line:
            res.suffixes.append((idx, "".join(d + csv_field(COLUMN_PREFIX + c, d) for c in columns)))
            continue
        rows = [r for r in parse_line(line, idx, ctx) if looks_like_title(r.info, r.title)]
        if rows:
            res.rows += 1
            values = [column_value(rows[0], c, opts) for c in columns]
        else:
            res.empty += 1
            values = [""] * len(columns)
        res.suffixes.append((idx, "".join(d + csv_field(v, d) for v in values)))
    return res


def annotate_lines(lines: List[Tuple[int, str]], ctx: Context, opts: Optional[Options] = None) -> List[Tuple[int, str]]:
    """[(zero-based line, annotation text)] for the lines that read like gun or ammo titles."""
    opts = opts or Options()
    out = []
    for idx, text in lines:
        if len(text) > 4000:
            continue
        rows = [r for r in parse_line(text, idx, ctx) if looks_like_title(r.info, r.title)]
        if not rows:
            continue
        note = annotation_text(rows[0], opts)
        if len(rows) > 1:
            note += " (+%d more)" % (len(rows) - 1)
        out.append((idx, note))
    return out
