#!/usr/bin/env python
"""Generate synthetic parser runs by degrading gold in controlled ways.

Two jobs:

1. **Calibrate the metrics.** A metric suite nobody has probed is as untrusted
   as an unvalidated gold. Each degradation targets one capability, so the
   score it moves tells us whether the metric measures what it claims. The
   `perfect` run must score exactly 1.000 on every track.
2. **Provide reference baselines.** `text_only` is roughly what a plain text
   extractor produces; real parsers can be read against it.

Usage:  synth.py            # writes runs/_synth_<name>/ for every degradation
"""
import copy
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "gold" / "pages"
RUNS = ROOT / "runs"


def to_ir(gold, name):
    """Gold -> parser-output IR, losslessly. This is the `perfect` run."""
    blocks = []
    for b in gold["blocks"]:
        nb = {"type": b["type"], "bbox": b["bbox"]}
        if b.get("text") is not None:
            nb["text"] = b["text"]
        for k in ("structure", "chart", "figure", "items", "marker_style", "level"):
            if k in b:
                nb[k] = copy.deepcopy(b[k])
        blocks.append(nb)
    return {"page_id": gold["page_id"], "parser": {"name": name, "version": "synthetic"},
            "blocks": blocks}


# --- degradations ---------------------------------------------------------

def d_perfect(ir, gold):
    return ir


def d_text_only(ir, gold):
    """A plain text extractor: tables flattened to text, no chart, no spans."""
    out = []
    for b in ir["blocks"]:
        if b["type"] == "chart":
            continue
        nb = {"type": "paragraph", "text": b.get("text", ""), "bbox": b["bbox"]}
        if not nb["text"]:
            continue
        out.append(nb)
    ir["blocks"] = out
    return ir


def d_dropped_na_cells(ir, gold):
    """The classic column-shift failure: cells carrying no value are omitted.

    Targets 'N/A' as well as blanks. Across this benchmark the tables hold just
    3 truly empty cells but 107 reading 'N/A', so dropping only blanks would
    barely register — the shift these pages actually invite comes from treating
    'N/A' as nothing.
    """
    for b in ir["blocks"]:
        if b["type"] != "table":
            continue
        st = b["structure"]
        hdr = st.get("header_rows", 0)
        kept, widest = [], 0
        for r in range(st["n_rows"]):
            row = sorted([c for c in st["cells"] if c["row"] == r], key=lambda c: c["col"])
            if r >= hdr:
                row = [c for c in row if c.get("text", "").strip() not in ("", "N/A")]
                # Re-pack into consecutive columns — this is the part that makes
                # it a real failure. Merely deleting the cells would leave blanks
                # at the same positions and shift nothing.
                for new_col, c in enumerate(row):
                    c["col"] = new_col
            widest = max(widest, len(row))
            kept += row
        st["cells"] = kept
        st["n_cols"] = max(widest, 1)
    return ir


def d_flat_header(ir, gold):
    """Loses merged cells: every span becomes 1x1."""
    for b in ir["blocks"]:
        if b["type"] == "table":
            for c in b["structure"]["cells"]:
                c["rowspan"] = c["colspan"] = 1
    return ir


def d_y_sorted(ir, gold):
    """Naive top-to-bottom ordering, ignoring columns."""
    ir["blocks"].sort(key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))
    return ir


def d_noisy_text(ir, gold, rate=0.02, seed=7):
    """2% character corruption — a stand-in for OCR noise."""
    rnd = random.Random(seed)
    alpha = "abcdefghijklmnopqrstuvwxyz "
    for b in ir["blocks"]:
        t = b.get("text")
        if not t:
            continue
        chars = list(t)
        for i in range(len(chars)):
            if rnd.random() < rate:
                chars[i] = rnd.choice(alpha)
        b["text"] = "".join(chars)
    return ir


def d_merged_paragraphs(ir, gold):
    """Fuses adjacent paragraphs — under-segmentation, text intact."""
    out, buf = [], None
    for b in ir["blocks"]:
        if b["type"] == "paragraph":
            if buf is None:
                buf = dict(b)
            else:
                buf["text"] += " " + b.get("text", "")
            continue
        if buf is not None:
            out.append(buf); buf = None
        out.append(b)
    if buf is not None:
        out.append(buf)
    ir["blocks"] = out
    return ir


def d_no_chart_labels(ir, gold):
    """Detects the chart but reads nothing inside it."""
    for b in ir["blocks"]:
        if b["type"] == "chart":
            b["chart"] = {"chart_type": "bubble", "data_labels": [],
                          "marks": {"n": 0, "by_class": {}}, "axes": {}}
    return ir


def d_half_chart_labels(ir, gold, seed=3):
    """Reads about half the chart labels — a plausible VLM result."""
    rnd = random.Random(seed)
    for b in ir["blocks"]:
        if b["type"] == "chart":
            labs = list(b["chart"].get("data_labels", []))
            rnd.shuffle(labs)
            b["chart"]["data_labels"] = sorted(labs[: len(labs) // 2])
    return ir


def d_alt_header(ir, gold):
    """Encodes p04's ambiguous header the OTHER acceptable way.

    Gold records row0/col0-2 as empty with the labels in row1; the alternative
    raises those labels into row0 with rowspan=2. Both readings are defensible,
    so this run must score ~1.0 on the table track. If it does not, the
    ambiguity allowance is not working.
    """
    import metrics as M
    for b in ir["blocks"]:
        if b["type"] == "table" and b["structure"].get("ambiguities"):
            for name, variant in M.ambiguity_variants(b["structure"]):
                if name != "as_encoded":
                    b["structure"] = variant
                    break
    return ir


DEGRADATIONS = {
    "perfect": d_perfect,
    "text_only": d_text_only,
    "dropped_na_cells": d_dropped_na_cells,
    "flat_header": d_flat_header,
    "y_sorted": d_y_sorted,
    "noisy_text": d_noisy_text,
    "merged_paragraphs": d_merged_paragraphs,
    "no_chart_labels": d_no_chart_labels,
    "half_chart_labels": d_half_chart_labels,
    "alt_header": d_alt_header,
}


def main():
    for name, fn in DEGRADATIONS.items():
        out = RUNS / f"_synth_{name}"
        out.mkdir(parents=True, exist_ok=True)
        for gp in sorted(GOLD.glob("*.json")):
            gold = json.loads(gp.read_text())
            ir = fn(to_ir(gold, f"synth:{name}"), gold)
            (out / gp.name).write_text(json.dumps(ir, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
