"""Shared helpers for assembling gold annotations.

Character content comes from the PDF text layer (the deck is digital-born, so
this is objective). Structure — block boundaries, types, table topology,
reading order — is supplied by hand in the per-page builders.
"""
import json
import re
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "benchmark" / "pages"
RENDERS = ROOT / "benchmark" / "renders"
GOLD = ROOT / "gold" / "pages"

SCHEMA_VERSION = "1.0"


_LITERALS = None


def literals(*path):
    """Fetch a page-specific text literal from tools/page_literals.json.

    Some gold values cannot be derived from geometry and have to be written
    down: the chart's data labels (they exist only as pixels), the bold run-in
    spans, the publisher name in a logo. Those strings are content of the source
    document, so they live in a data file that is NOT in version control rather
    than hardcoded in the builders — otherwise publishing the code would publish
    the document. See tools/page_literals.example.json for the shape.
    """
    global _LITERALS
    if _LITERALS is None:
        f = ROOT / "tools" / "page_literals.json"
        if not f.exists():
            raise SystemExit(
                f"missing {f.relative_to(ROOT)} — it holds the source document's text "
                f"literals and is excluded from version control. Copy "
                f"tools/page_literals.example.json and fill it in for your document.")
        _LITERALS = json.loads(f.read_text())
    node = _LITERALS
    for k in path:
        node = node[k]
    return node


def ws(s: str) -> str:
    """Collapse whitespace runs to one space; strip ends. Preserves \\n."""
    s = s.replace(" ", " ")
    parts = [re.sub(r"[ \t]+", " ", p).strip() for p in s.split("\n")]
    return "\n".join(parts).strip()


def load_lines(page_pdf: str):
    """Text-layer lines, sorted top-to-bottom then left-to-right."""
    doc = pymupdf.open(PAGES / page_pdf)
    page = doc[0]
    rows = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(s["text"] for s in line["spans"])
            if not text.strip():
                continue
            rows.append({
                "bbox": [round(v, 1) for v in line["bbox"]],
                "text": text,
                "bold": any("Bold" in s["font"] for s in line["spans"]),
                "sizes": sorted({round(s["size"], 1) for s in line["spans"]}),
                "colors": [s["color"] for s in line["spans"] if s["text"].strip()],
            })
    rows.sort(key=lambda r: (round(r["bbox"][1], 1), r["bbox"][0]))
    return page, rows


def union_bbox(boxes):
    return [round(min(b[0] for b in boxes), 1), round(min(b[1] for b in boxes), 1),
            round(max(b[2] for b in boxes), 1), round(max(b[3] for b in boxes), 1)]


def join(lines, idxs):
    """Join a run of wrapped lines into one logical text + its bbox."""
    sel = [lines[i] for i in idxs]
    return ws(" ".join(l["text"] for l in sel)), union_bbox([l["bbox"] for l in sel])


class PageBuilder:
    def __init__(self, page_id, page_pdf, render, page_number, profile, notes=""):
        self.page_id = page_id
        self.page, self.lines = load_lines(page_pdf)
        self.blocks = []
        self.meta = {
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "source": {
                "pdf": "parser-benchmark.pdf",
                "page_number": page_number,
                "page_pdf": f"benchmark/pages/{page_pdf}",
                "render": f"benchmark/renders/{render}",
            },
            "page": {
                "width_pt": round(self.page.rect.width, 1),
                "height_pt": round(self.page.rect.height, 1),
                "orientation": "landscape" if self.page.rect.width > self.page.rect.height else "portrait",
                "origin": "digital",
            },
            "annotation": {
                "method": "text-layer seed + visual verification against 200dpi render",
                "verified": True,
                "notes": notes,
            },
            "content_profile": profile,
        }

    def add(self, type_, text=None, bbox=None, lines=None, region="body",
            tracks=("text", "structure"), normalize=True, **extra):
        if lines is not None:
            text, bbox = join(self.lines, lines)
        blk = {
            "id": f"{self.page_id}.b{len(self.blocks) + 1:02d}",
            "type": type_,
            "reading_order": len(self.blocks) + 1,
            "bbox": bbox,
            "region": region,
            "tracks": list(tracks),
        }
        if text is not None:
            # Table text is a TSV rendering built from already-normalized cell
            # texts; running ws() over it would collapse the tab delimiters.
            blk["text"] = ws(text) if normalize else text
        blk.update(extra)
        self.blocks.append(blk)
        return blk

    def finish(self, extra_tracks=None):
        counts = {}
        for b in self.blocks:
            for t in b["tracks"]:
                counts[t] = counts.get(t, 0) + 1
        tracks = {
            "text": {"applicable": "text" in counts, "n_blocks": counts.get("text", 0)},
            "structure": {"applicable": True, "n_blocks": counts.get("structure", 0)},
            "table": {"applicable": "table" in counts,
                      "n_tables": sum(1 for b in self.blocks if b["type"] == "table")},
            "chart_data": {"applicable": "chart_data" in counts,
                           "n_charts": sum(1 for b in self.blocks if b["type"] == "chart")},
            "furniture": {"applicable": "furniture" in counts, "n_blocks": counts.get("furniture", 0)},
        }
        if extra_tracks:
            for k, v in extra_tracks.items():
                tracks.setdefault(k, {}).update(v)
        doc = dict(self.meta)
        doc["blocks"] = self.blocks
        doc["reading_order"] = [b["id"] for b in self.blocks]
        doc["tracks"] = tracks
        return doc

    def write(self, extra_tracks=None):
        doc = self.finish(extra_tracks)
        GOLD.mkdir(parents=True, exist_ok=True)
        out = GOLD / f"{self.page_id}.json"
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out.relative_to(ROOT)}  blocks={len(self.blocks)}")
        return doc


def tsv(cells, n_rows, n_cols):
    """Render a cell list as TSV for convenience text metrics."""
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for c in cells:
        grid[c["row"]][c["col"]] = c["text"]
    return "\n".join("\t".join(r) for r in grid)
