#!/usr/bin/env python
"""Gold builder — page 4: Executive Summary, wide 14-column table with a
two-level header.

Column model from the page's vertical rules (15 boundaries -> 14 columns):

  c0  Group            c7  Total Net Expense / Subject Fund
  c1  Fund             c8  Total Net Expense / Med.
  c2  Avg. AUM ($M)    c9  Total Net Expense incl. AFFE / Subject Fund
  c3  Net Advisory / Subject Fund     c10 ... / Med.
  c4  Net Advisory / Med.             c11 Total Return Rank / 1 Yr
  c5  Contractual Advisory / Subject Fund   c12 ... / 3 Yr
  c6  Contractual Advisory / Med.           c13 ... / 5 Yr

HEADER SHAPE — the one real judgement call on this page. The table top is
ragged: the rule at y=64.3 runs only from x=412.6 rightwards, so the group
headers occupy a band that does not exist above 'Group', 'Fund' and
'Avg. AUM ($M)'. Those three are boxed only between y=92.5 and y=118.5
(verified on a 500dpi crop: blank white space sits above them, with no border).
Gold therefore encodes row0/col0-2 as EMPTY header cells and places
'Group'/'Fund'/'Avg. AUM ($M)' in row1. Encoding them instead as rowspan=2 is
a defensible alternative reading and is declared in structure.ambiguities so a
scorer can accept it.

Header cells wrap over two text lines each ('Contractual' / 'Advisory²'); these
are joined. Footnote superscripts (¹²³⁴) are real characters in the text layer
and are kept.

Data cells carry a `color` when the page colours them — the deck uses colour to
encode quartile ranking (blue / green / tomato). This is genuine content but
almost no parser emits it, so it rides on the opt-in `cell_style` track.
"""
from goldlib import PageBuilder, join, tsv

NOTES = (
    "Landscape 14-column table with a two-level header and a RAGGED TOP: the group-"
    "header band exists only over columns 3-13. Gold encodes row0/col0-2 as empty "
    "cells with 'Group'/'Fund'/'Avg. AUM ($M)' in row1; a rowspan=2 reading is listed "
    "in structure.ambiguities as acceptable. Header labels wrap over two lines and are "
    "joined. All 27 body rows are fully populated (no blank cells); unavailable values "
    "are the literal string 'N/A', which a parser must reproduce rather than drop. Cell "
    "colour encodes quartile ranking and is recorded on the opt-in cell_style track."
)

COL_X = [18.2, 162.8, 359.6, 412.7, 447.6, 479.4, 514.4, 546.0,
         581.0, 612.7, 647.6, 679.3, 709.8, 740.5, 770.8]
N_COLS = len(COL_X) - 1  # 14
HEADER_TOP, HEADER_MID, HEADER_BOT = 64.3, 92.5, 118.5
BODY_BOT = 560.0

COLOR_NAMES = {0x008000: "green", 0xFF6347: "tomato", 0x0000FF: "blue"}


def col_of(bbox):
    cx = (bbox[0] + bbox[2]) / 2
    for i in range(N_COLS):
        if COL_X[i] - 0.6 <= cx < COL_X[i + 1] + 0.6:
            return i
    raise AssertionError(f"x-center {cx:.1f} outside column model")


b = PageBuilder(
    page_id="p04",
    page_pdf="p04_exec_summary_table.pdf",
    render="p04_exec_summary_table.png",
    page_number=4,
    profile=["table", "wide-table", "hierarchical-header"],
    notes=NOTES,
)
L = b.lines

b.add("heading", lines=[0], level=1)
b.add("banner", lines=[1])

cells = []

# --- header row 0: group headers, spanning. col0-2 intentionally empty. ---
for c in (0, 1, 2):
    cells.append({"row": 0, "col": c, "rowspan": 1, "colspan": 1,
                  "text": "", "is_header": True})
for col, span, idxs in [(3, 2, [5]), (5, 2, [2, 7]), (7, 2, [3, 8]),
                        (9, 2, [4, 9]), (11, 3, [6])]:
    cells.append({"row": 0, "col": col, "rowspan": 1, "colspan": span,
                  "text": join(L, idxs)[0], "is_header": True})

# --- header row 1: per-column sub-headers ---
ROW1 = [(0, [15]), (1, [16]), (2, [10, 24]), (3, [11, 25]), (4, [17]),
        (5, [12, 26]), (6, [18]), (7, [13, 27]), (8, [19]), (9, [14, 28]),
        (10, [20]), (11, [21]), (12, [22]), (13, [23])]
for col, idxs in ROW1:
    cells.append({"row": 1, "col": col, "rowspan": 1, "colspan": 1,
                  "text": join(L, idxs)[0], "is_header": True})

# --- body rows, assigned geometrically ---
body = [l for l in L if HEADER_BOT < l["bbox"][1] < BODY_BOT]
rows = []
for l in sorted(body, key=lambda r: (r["bbox"][1], r["bbox"][0])):
    if rows and abs(rows[-1][0]["bbox"][1] - l["bbox"][1]) < 4:
        rows[-1].append(l)
    else:
        rows.append([l])

n_blank = 0
for r, row_lines in enumerate(rows, start=2):
    seen = {}
    for l in row_lines:
        c = col_of(l["bbox"])
        assert c not in seen, f"row {r}: two texts in col {c}: {seen[c]!r} / {l['text']!r}"
        colors = {COLOR_NAMES[x] for x in l["colors"] if x in COLOR_NAMES}
        seen[c] = (l["text"].strip(), colors.pop() if len(colors) == 1 else None)
    for c in range(N_COLS):
        text, color = seen.get(c, ("", None))
        if not text:
            n_blank += 1
        cell = {"row": r, "col": c, "rowspan": 1, "colspan": 1,
                "text": text, "is_header": False}
        if color:
            cell["color"] = color
        cells.append(cell)

n_rows = 2 + len(rows)
print(f"  table: {n_rows} rows x {N_COLS} cols, {len(cells)} cells, {n_blank} blank body cells")

b.add("table", text=tsv(cells, n_rows, N_COLS), normalize=False,
      bbox=[18.2, HEADER_TOP, 770.8, round(rows[-1][0]["bbox"][3] + 2, 1)],
      tracks=("text", "structure", "table", "cell_style"),
      structure={
          "n_rows": n_rows, "n_cols": N_COLS, "header_rows": 2,
          "ambiguities": [{
              "cells": ["row0/col0", "row0/col1", "row0/col2"],
              "encoded_as": "empty header cells; labels live in row1",
              "accepted_alternative": "row1 labels raised to row0 with rowspan=2",
              "reason": "table top is ragged — the group-header band has no border "
                        "above columns 0-2, so those cells are visually single-row",
          }],
          "cells": cells,
      })

b.add("footer", lines=[408], region="footer", tracks=("furniture", "structure"))
b.add("footer", lines=[407], region="footer", tracks=("furniture", "structure"))
b.add("footer", lines=[409], region="footer", tracks=("furniture", "structure"))

b.write(extra_tracks={"cell_style": {"applicable": True, "opt_in": True,
                                     "note": "cell colour encodes quartile ranking"}})
