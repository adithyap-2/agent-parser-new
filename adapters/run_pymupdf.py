#!/usr/bin/env python
"""Baseline parser: PyMuPDF.

Runs against the page PDFs only — it never sees gold — and emits the benchmark
IR. This is the honest floor for a text-layer extractor: it reads the content
stream, finds ruled tables, and knows nothing about semantics.

Choices made here are the ones a competent engineer would make with this
library, so the score reflects PyMuPDF's real ceiling rather than a strawman:

* Block typing is heuristic: font size and weight relative to the page's modal
  body size decide heading vs paragraph; position decides header/footer.
* Tables come from `page.find_tables()`, PyMuPDF's own ruled-table detector.
  It reports a flat grid — no rowspan/colspan — which is a genuine limitation,
  not an adapter shortcut.
* Charts are not attempted; PyMuPDF has no chart understanding. Images are
  emitted as figures.

Usage:  run_pymupdf.py [--out runs/pymupdf]
"""
import argparse
import collections
import json
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "benchmark" / "pages"

PAGE_IDS = {"p04_exec_summary_table.pdf": "p04",
            "p13_bubble_chart.pdf": "p13",
            "p22_disclosures_text.pdf": "p22",
            "p27_notes_plus_tables.pdf": "p27",
            "p30_methodology_figures.pdf": "p30"}


def body_size(lines):
    c = collections.Counter()
    for ln in lines:
        c[round(ln["size"], 1)] += len(ln["text"])
    return c.most_common(1)[0][0] if c else 10.0


def classify(ln, base, page_h):
    y = ln["bbox"][1]
    if y > page_h * 0.90 or y < page_h * 0.04:
        return "footer" if y > page_h * 0.5 else "header"
    if ln["size"] >= base * 1.45:
        return "title"
    if ln["size"] >= base * 1.12 or (ln["bold"] and len(ln["text"]) < 90):
        return "heading"
    return "paragraph"


def extract_lines(page):
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for ln in blk["lines"]:
            txt = "".join(s["text"] for s in ln["spans"])
            if not txt.strip():
                continue
            out.append({
                "bbox": [round(v, 1) for v in ln["bbox"]],
                "text": txt,
                "size": max((s["size"] for s in ln["spans"]), default=10.0),
                "bold": any("Bold" in s["font"] or "Black" in s["font"] for s in ln["spans"]),
            })
    out.sort(key=lambda r: (round(r["bbox"][1], 1), r["bbox"][0]))
    return out


def group_paragraphs(lines, base, page_h):
    """Merge consecutive lines of the same class into blocks on a y-gap rule."""
    blocks = []
    for ln in lines:
        kind = classify(ln, base, page_h)
        if blocks:
            prev = blocks[-1]
            gap = ln["bbox"][1] - prev["lines"][-1]["bbox"][3]
            same_col = not (ln["bbox"][0] > prev["bbox"][2] or ln["bbox"][2] < prev["bbox"][0])
            if (prev["type"] == kind == "paragraph" and same_col
                    and gap < 0.75 * max(base, 1.0)):
                prev["lines"].append(ln)
                prev["bbox"] = [min(prev["bbox"][0], ln["bbox"][0]),
                                min(prev["bbox"][1], ln["bbox"][1]),
                                max(prev["bbox"][2], ln["bbox"][2]),
                                max(prev["bbox"][3], ln["bbox"][3])]
                continue
        blocks.append({"type": kind, "lines": [ln], "bbox": list(ln["bbox"])})
    for b in blocks:
        b["text"] = " ".join(l["text"] for l in b["lines"]).strip()
        b["text"] = " ".join(b["text"].split())
        del b["lines"]
    return blocks


def extract_tables(page):
    out = []
    try:
        finder = page.find_tables()
    except Exception:
        return out
    for t in finder.tables:
        rows = t.extract()
        if not rows:
            continue
        n_rows = len(rows)
        n_cols = max(len(r) for r in rows)
        cells = []
        header_rows = 0
        try:
            if t.header and t.header.names and not t.header.external:
                header_rows = 1
        except Exception:
            pass
        for r, row in enumerate(rows):
            for c in range(n_cols):
                val = row[c] if c < len(row) else None
                cells.append({"row": r, "col": c, "rowspan": 1, "colspan": 1,
                              "text": " ".join((val or "").split()),
                              "is_header": r < header_rows})
        out.append({"type": "table", "bbox": [round(v, 1) for v in t.bbox],
                    "structure": {"n_rows": n_rows, "n_cols": n_cols,
                                  "header_rows": header_rows, "cells": cells}})
    return out


def inside(inner, outer, pad=2.0):
    return (inner[0] >= outer[0] - pad and inner[1] >= outer[1] - pad
            and inner[2] <= outer[2] + pad and inner[3] <= outer[3] + pad)


def parse(pdf_path, page_id):
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    lines = extract_lines(page)
    base = body_size(lines)
    tables = extract_tables(page)
    tboxes = [t["bbox"] for t in tables]

    keep = [l for l in lines if not any(inside(l["bbox"], tb) for tb in tboxes)]
    blocks = group_paragraphs(keep, base, page.rect.height)

    for xref, *_ in page.get_images(full=True):
        for r in page.get_image_rects(xref):
            if r.width < 8 or r.height < 8:
                continue
            blocks.append({"type": "figure",
                           "bbox": [round(r.x0, 1), round(r.y0, 1),
                                    round(r.x1, 1), round(r.y1, 1)]})
    blocks += tables
    blocks.sort(key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))

    return {"page_id": page_id,
            "parser": {"name": "pymupdf", "version": pymupdf.version[0],
                       "notes": "text layer + find_tables(); no chart understanding"},
            "blocks": blocks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "runs" / "pymupdf"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for fname, pid in sorted(PAGE_IDS.items()):
        ir = parse(PAGES / fname, pid)
        (out / f"{pid}.json").write_text(json.dumps(ir, indent=1, ensure_ascii=False) + "\n")
        n_t = sum(1 for b in ir["blocks"] if b["type"] == "table")
        print(f"  {pid}: {len(ir['blocks'])} blocks, {n_t} table(s)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
