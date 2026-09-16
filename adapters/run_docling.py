#!/usr/bin/env python
"""Adapter: Docling -> benchmark IR.

Docling runs in its own Python 3.12 env (torch has no 3.14 wheels), so this is
executed with that interpreter:

    /opt/anaconda3/envs/docling/bin/python adapters/run_docling.py

It converts benchmark/benchmark-5page.pdf once and writes one IR file per page.

Mapping decisions, kept generous to Docling so the comparison stays fair:

* Reading order comes from `doc.iterate_items()`, which is Docling's own
  document order — not a geometric re-sort. Re-sorting would measure my
  adapter instead of the parser (a mistake that cost MinerU a whole page's
  reading-order score before it was caught).
* Consecutive `list_item`s are grouped into one `list` block, because gold
  encodes a bullet list as a single block. Emitting them individually would
  penalise Docling for a segmentation convention rather than an error.
* `page_header` / `page_footer` are emitted as furniture rather than dropped,
  so Docling gets credit on that track.
* Table cells carry Docling's real row/col spans, so its merged-cell handling
  is measured rather than flattened here.
* Charts: Docling has no chart-data extraction in the default pipeline, so the
  bitmap chart arrives as a picture. It scores 0 on chart_data, which is the
  honest result.

Docling reports bboxes bottom-left by default; they are converted to the IR's
top-left origin.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Page order in benchmark-5page.pdf, fixed when the subset was built.
PAGE_ORDER = ["p04", "p13", "p22", "p27", "p30"]

LABEL_MAP = {
    "title": "title",
    "section_header": "heading",
    "text": "paragraph",
    "paragraph": "paragraph",
    "caption": "caption",
    "footnote": "footnote",
    "page_header": "header",
    "page_footer": "footer",
    "list_item": "list_item",      # grouped into `list` below
    "table": "table",
    "picture": "figure",
    "chart": "figure",
    "formula": "paragraph",
    "code": "paragraph",
    "form": "paragraph",
    "key_value_region": "paragraph",
    "document_index": "paragraph",
}


def bbox_top_left(item, doc):
    """Docling bbox -> [x0, y0, x1, y1] with origin at the page top-left."""
    prov = getattr(item, "prov", None)
    if not prov:
        return None, None
    p = prov[0]
    page_no = getattr(p, "page_no", None)
    bb = getattr(p, "bbox", None)
    if bb is None:
        return page_no, None
    try:
        page = doc.pages[page_no]
        height = page.size.height
        bb = bb.to_top_left_origin(page_height=height)
    except Exception:
        pass
    x0, x1 = sorted((float(bb.l), float(bb.r)))
    y0, y1 = sorted((float(bb.t), float(bb.b)))
    return page_no, [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]


def table_structure(item):
    data = getattr(item, "data", None)
    cells = getattr(data, "table_cells", None) if data else None
    if not cells:
        return None
    out = []
    for c in cells:
        r0 = int(getattr(c, "start_row_offset_idx", 0))
        c0 = int(getattr(c, "start_col_offset_idx", 0))
        rs = int(getattr(c, "row_span", 0) or
                 (int(getattr(c, "end_row_offset_idx", r0 + 1)) - r0) or 1)
        cs = int(getattr(c, "col_span", 0) or
                 (int(getattr(c, "end_col_offset_idx", c0 + 1)) - c0) or 1)
        out.append({
            "row": r0, "col": c0, "rowspan": max(1, rs), "colspan": max(1, cs),
            "text": " ".join((getattr(c, "text", "") or "").split()),
            "is_header": bool(getattr(c, "column_header", False)),
        })
    if not out:
        return None
    n_rows = int(getattr(data, "num_rows", 0)) or max(c["row"] + c["rowspan"] for c in out)
    n_cols = int(getattr(data, "num_cols", 0)) or max(c["col"] + c["colspan"] for c in out)

    header_rows = 0
    for r in range(n_rows):
        in_row = [c for c in out if c["row"] == r]
        if in_row and all(c["is_header"] for c in in_row):
            header_rows = r + 1
        else:
            break
    return {"n_rows": n_rows, "n_cols": n_cols,
            "header_rows": header_rows, "cells": out}


def convert(pdf_path):
    from docling.document_converter import DocumentConverter
    conv = DocumentConverter()
    return conv.convert(str(pdf_path)).document


def _contains(outer, inner, pad=3.0):
    return (inner[0] >= outer[0] - pad and inner[1] >= outer[1] - pad
            and inner[2] <= outer[2] + pad and inner[3] <= outer[3] + pad)


def collect_skipped(doc):
    """Recover what `iterate_items()` does not yield.

    Two whole categories are invisible to that walk, and both matter here:

      * page_header / page_footer — detected by Docling but held outside
        doc.body, so a naive walk reports zero furniture.
      * text nested inside a picture — Docling's OCR reads bitmap regions, and
        on the rasterised chart page that is the ONLY way the bubble labels can
        be recovered. iterate_items() does not descend into pictures by
        default, so this content is silently dropped.

    Returns (furniture_items, ocr_items) keyed by page number.
    """
    in_body = {id(it) for it, _ in doc.iterate_items()}
    furniture, ocr = {}, {}
    for t in doc.texts:
        if id(t) in in_body:
            continue
        label = str(getattr(t, "label", "")).split(".")[-1].lower()
        page_no, bbox = bbox_top_left(t, doc)
        if page_no is None:
            continue
        text = " ".join((getattr(t, "text", "") or "").split())
        if not text:
            continue
        if label in ("page_header", "page_footer"):
            furniture.setdefault(page_no, []).append(
                {"type": "header" if label == "page_header" else "footer",
                 "bbox": bbox, "text": text})
        else:
            ocr.setdefault(page_no, []).append({"bbox": bbox, "text": text})
    return furniture, ocr


def build_pages(doc, version):
    pages = {pid: [] for pid in PAGE_ORDER}
    pictures = {}          # page_no -> list of picture bboxes

    for item, _level in doc.iterate_items():
        label = str(getattr(item, "label", "") or "")
        label = label.split(".")[-1].lower()
        kind = LABEL_MAP.get(label)
        if kind is None:
            kind = "paragraph"
        page_no, bbox = bbox_top_left(item, doc)
        if page_no is None or not (1 <= page_no <= len(PAGE_ORDER)):
            continue
        pid = PAGE_ORDER[page_no - 1]

        if kind == "table":
            st = table_structure(item)
            blk = {"type": "table", "bbox": bbox}
            if st:
                blk["structure"] = st
            else:
                txt = " ".join((getattr(item, "text", "") or "").split())
                if not txt:
                    continue
                blk = {"type": "paragraph", "bbox": bbox, "text": txt}
            pages[pid].append(blk)
            continue

        if kind == "figure":
            pages[pid].append({"type": "figure", "bbox": bbox})
            if bbox:
                pictures.setdefault(page_no, []).append(bbox)
            continue

        text = " ".join((getattr(item, "text", "") or "").split())
        if not text:
            continue
        pages[pid].append({"type": kind, "bbox": bbox, "text": text})

    # --- recover furniture and picture-nested OCR text ----------------------
    furniture, ocr = collect_skipped(doc)

    for page_no, items in furniture.items():
        if not (1 <= page_no <= len(PAGE_ORDER)):
            continue
        blocks = pages[PAGE_ORDER[page_no - 1]]
        tops = [b["bbox"][1] for b in blocks if b.get("bbox")]
        for it in items:
            pos = sum(1 for t in tops if t < it["bbox"][1]) if it.get("bbox") else len(blocks)
            blocks.insert(pos, it)
            if it.get("bbox"):
                tops.insert(pos, it["bbox"][1])

    # OCR text that falls inside a picture is that picture's content. On the
    # chart page this is the bubble labels, so it becomes a chart payload.
    # Pure numeric/percent tokens are axis ticks, not data labels; that filter
    # is a generic rule, not derived from gold.
    import re
    TICK = re.compile(r"^[-+]?\d+(\.\d+)?%?$")
    for page_no, items in ocr.items():
        if not (1 <= page_no <= len(PAGE_ORDER)):
            continue
        boxes = pictures.get(page_no) or []
        inside = [it for it in items
                  if it.get("bbox") and any(_contains(b, it["bbox"]) for b in boxes)]
        if not inside:
            continue
        labels = sorted({it["text"] for it in inside if not TICK.match(it["text"])})
        ticks = sorted({it["text"] for it in inside if TICK.match(it["text"])})
        blocks = pages[PAGE_ORDER[page_no - 1]]
        for b in blocks:
            if b["type"] == "figure" and b.get("bbox") and any(
                    _contains(b["bbox"], it["bbox"]) for it in inside):
                b["type"] = "chart"
                b["chart"] = {
                    "chart_type": "unknown",
                    "data_labels": labels,
                    "axes": {"x": {"ticks": ticks}, "y": {"ticks": ticks}},
                    "source": "rapidocr text nested inside the picture element; "
                              "not surfaced by iterate_items()",
                }
                break

    # Merge runs of list_item into a single `list` block, matching gold's
    # convention. Docling emits one item per bullet.
    out = {}
    for pid, blocks in pages.items():
        merged, buf = [], []

        def flush():
            if not buf:
                return
            xs = [b["bbox"] for b in buf if b.get("bbox")]
            bb = ([min(b[0] for b in xs), min(b[1] for b in xs),
                   max(b[2] for b in xs), max(b[3] for b in xs)] if xs else None)
            merged.append({
                "type": "list", "bbox": bb,
                "text": "\n".join(b["text"] for b in buf),
                "items": [{"text": b["text"], "level": 0, "marker_raw": ""} for b in buf],
            })
            buf.clear()

        for b in blocks:
            if b["type"] == "list_item":
                buf.append(b)
            else:
                flush()
                merged.append(b)
        flush()
        out[pid] = merged

    return {pid: {"page_id": pid,
                  "parser": {"name": "docling", "version": version,
                             "notes": "default pipeline; iterate_items() reading order"},
                  "blocks": blocks}
            for pid, blocks in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(ROOT / "benchmark" / "benchmark-5page.pdf"))
    ap.add_argument("--out", default=str(ROOT / "runs" / "docling"))
    a = ap.parse_args()

    try:
        from importlib.metadata import version as _v
        ver = _v("docling")
    except Exception:
        ver = "unknown"

    print(f"converting {a.pdf} with docling {ver} ...")
    doc = convert(a.pdf)
    pages = build_pages(doc, ver)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for pid in PAGE_ORDER:
        ir = pages[pid]
        (out / f"{pid}.json").write_text(json.dumps(ir, indent=1, ensure_ascii=False) + "\n")
        n_t = sum(1 for b in ir["blocks"] if b["type"] == "table")
        n_f = sum(1 for b in ir["blocks"] if b["type"] == "figure")
        n_l = sum(1 for b in ir["blocks"] if b["type"] == "list")
        print(f"  {pid}: {len(ir['blocks'])} blocks, {n_t} table(s), "
              f"{n_f} figure(s), {n_l} list(s)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
