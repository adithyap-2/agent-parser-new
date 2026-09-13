#!/usr/bin/env python
"""Gold builder — page 27: 'Project Specific Notes', prose + two ruled tables.

Table topology is taken from the page's own vector rules, not guessed from text
positions:

  vertical rules   x = 77.4, 253.2, 366.4, 479.6, 533.2   (4 ruled column groups)
  table 1 horizontals y = 272.2, 294.6, 407.3, 441.0
  table 2 horizontals y = 452.3, 474.8, 576.1, 610.0

Only four column groups are ruled, but the "Total Return" and "Sharpe" groups
each carry three unruled sub-columns (1/3/5 Year) and "Std. Deviation" carries
one. Logical grid is therefore 8 columns:

  col0 Fund | col1-3 Total Return | col4-6 Sharpe | col7 Std. Deviation

There is no horizontal rule between the two header text rows, so the "Fund"
cell spans them: row0/col0 is rowspan=2. "Std. Deviation" does NOT span rows —
row1/col7 holds its own "3 Year" sub-header.

Row banding (grey fills on alternate data rows) is presentation only and is
not encoded. Bold on the subject-fund row and on the three summary rows is
noted but not scored.
"""
import sys

from goldlib import PageBuilder, tsv, literals

NOTES = (
    "Portrait page mixing headings, prose and two ruled tables with identical "
    "geometry. Both tables use a two-level header: three group headers spanning "
    "unruled sub-columns, with the 'Fund' cell merged across both header rows "
    "(rowspan=2). 'Std. Deviation' spans one column only. Cell topology was read "
    "from the page's vector rules. Alternate-row grey banding and the bold subject-"
    "fund/summary rows are presentation and are not encoded. The heading "
    "'Supplemental Performance vs. Sharpe Ratio Data:' is underlined, not bold."
)

# Column model, from the vector rules. Ruled groups split into equal sub-columns.
GROUPS = [(77.4, 253.2, 1), (253.2, 366.4, 3), (366.4, 479.6, 3), (479.6, 533.2, 1)]
COL_EDGES = []
for x0, x1, n in GROUPS:
    step = (x1 - x0) / n
    COL_EDGES += [(x0 + i * step, x0 + (i + 1) * step) for i in range(n)]
N_COLS = len(COL_EDGES)  # 8

SUB_HEADERS = ["1 Year", "3 Year", "5 Year", "1 Year", "3 Year", "5 Year", "3 Year"]


def col_of(bbox):
    cx = (bbox[0] + bbox[2]) / 2
    for i, (a, b) in enumerate(COL_EDGES):
        if a - 0.5 <= cx < b + 0.5:
            return i
    raise AssertionError(f"x-center {cx:.1f} falls outside the column model")


def build_table(lines, y_top, y_bot, y_header_end, label):
    """Assemble one table. Header rows are hand-specified; data rows geometric."""
    body = [l for l in lines if y_header_end < l["bbox"][1] < y_bot]

    # Group data lines into rows by y.
    rows = []
    for l in sorted(body, key=lambda r: (r["bbox"][1], r["bbox"][0])):
        if rows and abs(rows[-1][0]["bbox"][1] - l["bbox"][1]) < 3:
            rows[-1].append(l)
        else:
            rows.append([l])

    cells = [
        {"row": 0, "col": 0, "rowspan": 2, "colspan": 1, "text": "Fund", "is_header": True},
        {"row": 0, "col": 1, "rowspan": 1, "colspan": 3, "text": "Total Return", "is_header": True},
        {"row": 0, "col": 4, "rowspan": 1, "colspan": 3, "text": "Sharpe", "is_header": True},
        {"row": 0, "col": 7, "rowspan": 1, "colspan": 1, "text": "Std. Deviation", "is_header": True},
    ]
    for i, h in enumerate(SUB_HEADERS):
        cells.append({"row": 1, "col": i + 1, "rowspan": 1, "colspan": 1,
                      "text": h, "is_header": True})

    for r, row_lines in enumerate(rows, start=2):
        seen = {}
        for l in row_lines:
            c = col_of(l["bbox"])
            assert c not in seen, f"{label}: two texts in row {r} col {c}"
            seen[c] = l["text"].strip()
        assert set(seen) == set(range(N_COLS)), \
            f"{label}: row {r} has columns {sorted(seen)}, expected 0..{N_COLS-1}"
        for c in range(N_COLS):
            cells.append({"row": r, "col": c, "rowspan": 1, "colspan": 1,
                          "text": seen[c], "is_header": False})

    n_rows = 2 + len(rows)
    return cells, n_rows


b = PageBuilder(
    page_id="p27",
    page_pdf="p27_notes_plus_tables.pdf",
    render="p27_notes_plus_tables.png",
    page_number=27,
    profile=["prose", "table", "mixed"],
    notes=NOTES,
)
L = b.lines

b.add("title", lines=[0])
b.add("heading", lines=[1], level=2, bold_spans=[literals("p27", "headings")[0]])
b.add("paragraph", lines=[2])
b.add("heading", lines=[3], level=2, bold_spans=[literals("p27", "headings")[1]])
b.add("paragraph", lines=[4, 5, 6])
b.add("heading", lines=[7], level=3, underlined=True)
b.add("paragraph", lines=[8, 9, 10, 11])

for label, (y0, y1, yh) in {
    "table-1": (272.2, 441.6, 294.6),
    "table-2": (452.3, 610.5, 474.8),
}.items():
    cells, n_rows = build_table(L, y0, y1, yh, label)
    b.add("table", text=tsv(cells, n_rows, N_COLS), normalize=False,
          bbox=[77.4, y0, 533.8, y1], tracks=("text", "structure", "table"),
          structure={"n_rows": n_rows, "n_cols": N_COLS, "header_rows": 2, "cells": cells})
    print(f"  {label}: {n_rows} rows x {N_COLS} cols, {len(cells)} cells")

b.add("footer", lines=[234], region="footer", tracks=("furniture", "structure"))
b.add("figure", text=None, bbox=[467.0, 734.0, 538.0, 777.0], region="footer",
      tracks=("furniture", "structure"),
      figure={"kind": "logo", "raster": {"xref": 581, "px": [588, 359]},
              "description": literals("logo", "description"), "contains_text": True,
              "text_in_image": literals("logo", "text_in_image")})
b.add("footer", lines=[235], region="footer", tracks=("furniture", "structure"))

b.write()
