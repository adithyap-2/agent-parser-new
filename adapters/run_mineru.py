#!/usr/bin/env python
"""Adapter: MinerU pipeline output -> benchmark IR.

MinerU is run separately (it needs its own Python 3.12 env, since torch has no
3.14 wheels):

    MINERU_MODEL_SOURCE=modelscope mineru \\
        -p benchmark/benchmark-5page.pdf -o /tmp/mineru_out -b pipeline -m txt

This reads the resulting `*_middle.json`, which carries per-page layout blocks
with bboxes, types, and — for tables — recognised HTML. The flat
`*_content_list.json` is easier to read but drops bboxes and block nesting, so
it would understate MinerU on the structure track.

Mapping decisions (kept generous to MinerU, so the comparison is fair):

* `title` -> heading, `text` -> paragraph, `list` -> list, `image` -> figure.
* `discarded_blocks` are MinerU's detected headers/footers. They are emitted as
  `footer`/`header` rather than dropped, so MinerU gets credit on the furniture
  track instead of being silently penalised for filtering them.
* Table HTML is converted to real IR cells WITH rowspan/colspan (see
  html_table.py), so MinerU's merged-cell handling is measured rather than
  flattened by the adapter.
* Charts: MinerU's pipeline backend has no chart-data extraction, so chart
  blocks come through as figures. It scores 0 on chart_data, which is the
  honest result for this backend.
"""
import argparse
import json
from pathlib import Path

from html_table import html_to_structure

ROOT = Path(__file__).resolve().parent.parent

# Page order in benchmark-5page.pdf, set when the subset was built with pdfunite.
PAGE_ORDER = ["p04", "p13", "p22", "p27", "p30"]

TYPE_MAP = {
    "title": "heading",
    "text": "paragraph",
    "list": "list",
    "index": "paragraph",
    "image": "figure",
    "table": "table",
    "equation": "paragraph",
    "interline_equation": "paragraph",
    # MinerU has a 'chart' block type, but the pipeline backend detects the
    # region without extracting series data. Mapping it to `figure` is honest
    # about what is recoverable; it scores the same on coarse type either way,
    # and chart_data scores 0 regardless because no payload is produced.
    "chart": "figure",
    "code": "paragraph",
    "discarded": "footer",
}


def collect_text(node):
    """Walk MinerU's block -> lines -> spans nesting and gather content."""
    out = []
    if isinstance(node, dict):
        if "content" in node and isinstance(node["content"], str):
            out.append(node["content"])
        for key in ("blocks", "lines", "spans"):
            for child in node.get(key, []) or []:
                out.append(collect_text(child))
    elif isinstance(node, list):
        for child in node:
            out.append(collect_text(child))
    return " ".join(x for x in out if x)


def find_html(node):
    if isinstance(node, dict):
        if isinstance(node.get("html"), str) and "<t" in node["html"]:
            return node["html"]
        for key in ("blocks", "lines", "spans"):
            for child in node.get(key, []) or []:
                r = find_html(child)
                if r:
                    return r
    elif isinstance(node, list):
        for child in node:
            r = find_html(child)
            if r:
                return r
    return None


def bbox_of(b):
    bb = b.get("bbox") or [0, 0, 1, 1]
    return [round(float(v), 1) for v in bb]


def convert_block(b, region="body"):
    raw = b.get("type", "text")
    kind = TYPE_MAP.get(raw, "paragraph")
    blk = {"type": kind, "bbox": bbox_of(b)}

    if kind == "table":
        html = find_html(b)
        st = html_to_structure(html) if html else None
        if st:
            blk["structure"] = st
        cap = collect_text({"blocks": [x for x in b.get("blocks", [])
                                       if x.get("type") in ("table_caption", "table_footnote")]})
        if cap:
            blk["caption"] = cap
        if not st:
            txt = collect_text(b)
            if not txt:
                return None
            blk["type"] = "paragraph"
            blk["text"] = txt
        return blk

    if kind == "figure":
        return blk

    text = collect_text(b)
    if not text.strip():
        return None
    blk["text"] = " ".join(text.split())
    if region == "furniture":
        y = blk["bbox"][1]
        blk["type"] = "footer" if y > 400 else "header"
    return blk


def convert_page(page, page_id, mineru_version):
    src = page.get("para_blocks") or page.get("preproc_blocks") or []
    blocks = [nb for nb in (convert_block(b) for b in src) if nb]

    # MinerU's `discarded_blocks` (its detected headers/footers) are omitted
    # from its own markdown, so they carry no reading position. Appending them
    # at the end would invent an ordering error the parser never made — on p04
    # that alone put the page heading after the table and drove reading-order
    # tau to 0. Instead each one is inserted at the position its bbox implies,
    # leaving the relative order of para_blocks (MinerU's actual reading order)
    # untouched.
    tops = [b["bbox"][1] for b in blocks]
    for b in page.get("discarded_blocks", []) or []:
        nb = convert_block(b, region="furniture")
        if not nb:
            continue
        pos = sum(1 for t in tops if t < nb["bbox"][1])
        blocks.insert(pos, nb)
        tops.insert(pos, nb["bbox"][1])
    return {"page_id": page_id,
            "parser": {"name": "mineru", "version": mineru_version,
                       "notes": "pipeline backend, -m txt; tables via HTML recognition"},
            "blocks": blocks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--middle", default=None, help="path to *_middle.json")
    ap.add_argument("--mineru-out", default="/tmp/mineru_out")
    ap.add_argument("--out", default=str(ROOT / "runs" / "mineru"))
    ap.add_argument("--version", default="3.4.5")
    a = ap.parse_args()

    mid = Path(a.middle) if a.middle else None
    if mid is None:
        found = sorted(Path(a.mineru_out).rglob("*middle.json"))
        if not found:
            raise SystemExit(f"no *_middle.json under {a.mineru_out}")
        mid = found[0]
    print(f"reading {mid}")

    data = json.loads(mid.read_text())
    pages = data.get("pdf_info") or []
    if len(pages) != len(PAGE_ORDER):
        print(f"  warning: {len(pages)} pages in output, expected {len(PAGE_ORDER)}")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for idx, page in enumerate(pages):
        if idx >= len(PAGE_ORDER):
            break
        pid = PAGE_ORDER[idx]
        ir = convert_page(page, pid, a.version)
        (out / f"{pid}.json").write_text(json.dumps(ir, indent=1, ensure_ascii=False) + "\n")
        n_t = sum(1 for b in ir["blocks"] if b["type"] == "table")
        n_f = sum(1 for b in ir["blocks"] if b["type"] == "figure")
        print(f"  {pid}: {len(ir['blocks'])} blocks, {n_t} table(s), {n_f} figure(s)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
