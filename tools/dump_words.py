#!/usr/bin/env python
"""Dump the PDF text layer with geometry, for hand-building gold annotations.

Usage:
    dump_words.py <pdf> [--mode words|lines|blocks|spans] [--page N]

The source deck is digital-born, so the character content of each page is
objective ground truth; only the *structure* over it is a judgement call.
This tool surfaces the former so the latter can be done by hand.
"""
import argparse
import json
import sys

import pymupdf


def dump(path, mode, page_no):
    doc = pymupdf.open(path)
    page = doc[page_no]
    out = {"page": page_no, "width": page.rect.width, "height": page.rect.height}

    if mode == "words":
        # (x0, y0, x1, y1, word, block_no, line_no, word_no)
        out["words"] = [
            {"bbox": [round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1)],
             "text": w[4], "block": w[5], "line": w[6], "word": w[7]}
            for w in page.get_text("words")
        ]
    elif mode == "lines":
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
                    "sizes": sorted({round(s["size"], 1) for s in line["spans"]}),
                    "fonts": sorted({s["font"] for s in line["spans"]}),
                })
        rows.sort(key=lambda r: (round(r["bbox"][1], 0), r["bbox"][0]))
        out["lines"] = rows
    elif mode == "spans":
        rows = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for s in line["spans"]:
                    if not s["text"].strip():
                        continue
                    rows.append({
                        "bbox": [round(v, 1) for v in s["bbox"]],
                        "text": s["text"],
                        "size": round(s["size"], 1),
                        "font": s["font"],
                        "color": s["color"],
                    })
        rows.sort(key=lambda r: (round(r["bbox"][1], 0), r["bbox"][0]))
        out["spans"] = rows
    elif mode == "blocks":
        out["blocks"] = [
            {"bbox": [round(v, 1) for v in b["bbox"]],
             "type": "text" if b["type"] == 0 else "image",
             "text": (b.get("lines") and "\n".join(
                 "".join(s["text"] for s in ln["spans"]) for ln in b["lines"])) or ""}
            for b in page.get_text("dict")["blocks"]
        ]
    else:
        sys.exit(f"unknown mode {mode}")

    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--mode", default="lines")
    ap.add_argument("--page", type=int, default=0)
    a = ap.parse_args()
    dump(a.pdf, a.mode, a.page)
