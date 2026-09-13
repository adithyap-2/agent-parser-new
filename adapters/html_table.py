"""Parse an HTML table into benchmark-IR cells.

MinerU's table recognition emits HTML, so spans arrive as rowspan/colspan
attributes. Converting them to the IR's logical grid needs an occupancy map:
a cell with rowspan=2 reserves its column in the NEXT row too, which shifts
every later cell in that row. Walking the HTML naively and assigning
col = position-in-row silently corrupts any table with merged cells.
"""
from html.parser import HTMLParser


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []          # list of list of (text, rowspan, colspan, is_header)
        self._row = None
        self._cell = None
        self._buf = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._depth += 1
        elif tag == "tr" and self._depth:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            def num(k):
                try:
                    return max(1, int(a.get(k, 1)))
                except (TypeError, ValueError):
                    return 1
            self._cell = [num("rowspan"), num("colspan"), tag == "th"]
            self._buf = []
        elif tag == "br" and self._cell is not None:
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            text = " ".join("".join(self._buf).split())
            self._row.append((text, self._cell[0], self._cell[1], self._cell[2]))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._cell is not None:
            self._buf.append(data)


def html_to_structure(html: str):
    """Return an IR `structure` dict, or None if no table was found."""
    p = _TableParser()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        return None
    if not p.rows:
        return None

    occupied = {}          # (row, col) -> True, reserved by earlier rowspans
    cells = []
    n_cols = 0
    for r, row in enumerate(p.rows):
        c = 0
        for text, rs, cs, is_h in row:
            while (r, c) in occupied:
                c += 1                      # skip columns held by a rowspan above
            cells.append({"row": r, "col": c, "rowspan": rs, "colspan": cs,
                          "text": text, "is_header": is_h})
            for dr in range(rs):
                for dc in range(cs):
                    occupied[(r + dr, c + dc)] = True
            c += cs
            n_cols = max(n_cols, c)
    n_rows = max((c["row"] + c["rowspan"] for c in cells), default=0)

    # A header row is one whose cells are all <th>, counting from the top only.
    header_rows = 0
    for r in range(n_rows):
        in_row = [c for c in cells if c["row"] == r]
        if in_row and all(c["is_header"] for c in in_row):
            header_rows = r + 1
        else:
            break
    return {"n_rows": n_rows, "n_cols": n_cols,
            "header_rows": header_rows, "cells": cells}
