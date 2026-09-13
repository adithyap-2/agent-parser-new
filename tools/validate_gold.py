#!/usr/bin/env python
"""Validate the gold files: schema, geometry, table topology, text coverage.

The coverage check is the important one. Because the deck is digital-born, the
PDF text layer is an independent record of exactly which characters are on each
page. Comparing it against the characters in the gold blocks catches both
failure directions: text silently dropped during annotation, and text invented
that is not on the page.

Exclusions, all deliberate:
  * list markers (U+F0B7, U+2022) — presentation, stripped from item text
  * chart blocks — page 13's data labels come from the raster, not the text
    layer, so they cannot appear in a text-layer comparison
  * whitespace — gold normalises wrapping
"""
import collections
import json
import sys
from pathlib import Path

import pymupdf

from goldlib import GOLD, ROOT

TYPES = {"title", "heading", "banner", "paragraph", "list", "table", "chart",
         "figure", "caption", "footnote", "header", "footer"}
TRACKS = {"text", "structure", "table", "chart_data", "furniture", "cell_style"}
MARKERS = "\uf0b7\u2022"  # Symbol-font private-use bullet, and U+2022

errors, warnings = [], []


def err(page, msg):
    errors.append(f"[{page}] {msg}")


def warn(page, msg):
    warnings.append(f"[{page}] {msg}")


def norm(s):
    return "".join(ch for ch in s if not ch.isspace() and ch not in MARKERS)


def check_table(pid, blk):
    st = blk.get("structure")
    if not st:
        return err(pid, f"{blk['id']}: table block has no structure")
    R, C = st["n_rows"], st["n_cols"]
    grid = [[None] * C for _ in range(R)]
    for c in st["cells"]:
        rs, cs = c.get("rowspan", 1), c.get("colspan", 1)
        if c["row"] + rs > R or c["col"] + cs > C:
            err(pid, f"{blk['id']}: cell ({c['row']},{c['col']}) span exits the grid")
            continue
        for r in range(c["row"], c["row"] + rs):
            for k in range(c["col"], c["col"] + cs):
                if grid[r][k] is not None:
                    err(pid, f"{blk['id']}: cell ({r},{k}) covered twice")
                grid[r][k] = c
    holes = [(r, k) for r in range(R) for k in range(C) if grid[r][k] is None]
    if holes:
        err(pid, f"{blk['id']}: {len(holes)} uncovered grid position(s), e.g. {holes[:4]}")
    hdr = st.get("header_rows", 0)
    for c in st["cells"]:
        if c["row"] < hdr and not c.get("is_header"):
            err(pid, f"{blk['id']}: cell ({c['row']},{c['col']}) in a header row is not is_header")


def check_page(path):
    doc = json.loads(path.read_text())
    pid = doc["page_id"]

    src = doc["source"]
    page_pdf = ROOT / src["page_pdf"]
    if not page_pdf.exists():
        return err(pid, f"missing page pdf {src['page_pdf']}")
    if not (ROOT / src["render"]).exists():
        err(pid, f"missing render {src['render']}")

    pg = pymupdf.open(page_pdf)[0]
    W, H = pg.rect.width, pg.rect.height
    if abs(W - doc["page"]["width_pt"]) > 0.6 or abs(H - doc["page"]["height_pt"]) > 0.6:
        err(pid, "page dimensions disagree with the PDF")

    # --- blocks -----------------------------------------------------------
    ids = [b["id"] for b in doc["blocks"]]
    if len(set(ids)) != len(ids):
        err(pid, "duplicate block ids")
    for i, blk in enumerate(doc["blocks"], start=1):
        if blk["type"] not in TYPES:
            err(pid, f"{blk['id']}: unknown type {blk['type']!r}")
        if blk["reading_order"] != i:
            err(pid, f"{blk['id']}: reading_order {blk['reading_order']} != position {i}")
        if blk["id"] != f"{pid}.b{i:02d}":
            err(pid, f"{blk['id']}: id does not match its position")
        bad = set(blk["tracks"]) - TRACKS
        if bad:
            err(pid, f"{blk['id']}: unknown track(s) {bad}")
        x0, y0, x1, y1 = blk["bbox"]
        if not (0 <= x0 < x1 <= W + 1 and 0 <= y0 < y1 <= H + 1):
            err(pid, f"{blk['id']}: bbox {blk['bbox']} outside the page ({W}x{H})")
        if blk["type"] == "table":
            check_table(pid, blk)
        if blk["type"] == "list":
            if not blk.get("items"):
                err(pid, f"{blk['id']}: list has no items")
            joined = "\n".join(i["text"] for i in blk["items"])
            if joined != blk.get("text"):
                err(pid, f"{blk['id']}: list text is not its items joined by newline")
        if blk["type"] == "chart" and "chart" not in blk:
            err(pid, f"{blk['id']}: chart block has no chart payload")
        if blk["type"] == "figure" and "figure" not in blk:
            err(pid, f"{blk['id']}: figure block has no figure payload")
        if blk.get("caption_for") and blk["caption_for"] not in ids:
            err(pid, f"{blk['id']}: caption_for points at unknown block")

    if doc["reading_order"] != ids:
        err(pid, "reading_order[] does not match block order")

    # --- text coverage vs the PDF text layer ------------------------------
    pdf_chars = collections.Counter(norm(pg.get_text()))
    gold_chars = collections.Counter()
    for blk in doc["blocks"]:
        if blk["type"] == "chart":
            continue
        gold_chars.update(norm(blk.get("text") or ""))

    missing = pdf_chars - gold_chars      # on the page, absent from gold
    extra = gold_chars - pdf_chars        # in gold, not on the page
    if missing:
        err(pid, f"{sum(missing.values())} char(s) on the page missing from gold: "
                 f"{dict(missing.most_common(8))}")
    if extra:
        err(pid, f"{sum(extra.values())} char(s) in gold not on the page: "
                 f"{dict(extra.most_common(8))}")

    tr = doc.get("tracks", {})
    for name, spec in tr.items():
        if name not in TRACKS:
            err(pid, f"unknown track {name!r}")
        declared = sum(1 for b in doc["blocks"] if name in b["tracks"])
        if spec.get("applicable") and "n_blocks" in spec and spec["n_blocks"] != declared:
            err(pid, f"track {name}: n_blocks {spec['n_blocks']} != {declared} actual")

    n_txt = sum(1 for b in doc["blocks"] if b.get("text"))
    return (pid, len(doc["blocks"]), n_txt,
            sum(pdf_chars.values()), sum(gold_chars.values()))


def main():
    files = sorted(GOLD.glob("*.json"))
    if not files:
        sys.exit("no gold files found")
    print(f"{'page':6s} {'blocks':>6s} {'w/text':>6s} {'pdf_chars':>10s} {'gold_chars':>11s}")
    for f in files:
        r = check_page(f)
        if r:
            print(f"{r[0]:6s} {r[1]:6d} {r[2]:6d} {r[3]:10d} {r[4]:11d}")

    print()
    for w in warnings:
        print("WARN ", w)
    if errors:
        for e in errors:
            print("ERROR", e)
        sys.exit(f"\n{len(errors)} error(s)")
    print(f"OK — {len(files)} page(s) valid, 0 errors, {len(warnings)} warning(s)")


if __name__ == "__main__":
    main()
