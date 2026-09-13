#!/usr/bin/env python
"""Score a parser run against the gold standard.

Usage:
    score.py runs/<parser>/            # score every page found
    score.py runs/<parser>/ --level L0 --json results/<parser>.json

A run is one JSON file per page in the parser-output IR (see bench/SPEC.md):

    {"page_id": "p04",
     "parser": {"name": "...", "version": "..."},
     "blocks": [ {"type": ..., "text": ..., "bbox": [...],
                  "structure": {...},   # tables
                  "chart": {...}} ]}    # charts

Blocks are given in the parser's reading order. Everything except `type` and
`text` is optional; a parser that emits nothing but text still scores on the
text track.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import metrics as M
from normalize import normalize

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "gold" / "pages"

# Coarse type vocabulary. Parsers disagree wildly on fine-grained names
# ('Title' vs 'Section-header' vs 'H1'), so type accuracy is reported at both
# levels: strict for parsers that share our vocabulary, coarse for the rest.
COARSE = {
    "title": "heading", "heading": "heading", "banner": "heading",
    "paragraph": "text", "caption": "text", "footnote": "text",
    "list": "list", "table": "table",
    "chart": "figure", "figure": "figure",
    "header": "furniture", "footer": "furniture",
}

# Per-page track weights. Each page is in the benchmark to stress specific
# capabilities; weights say so explicitly rather than hiding it in an average.
PAGE_WEIGHTS = {
    # wide hierarchical table dominates; prose is minimal
    "p04": {"table": 0.65, "text": 0.15, "structure": 0.20},
    # rasterised chart, plus a reading-order trap in the two-column footer
    "p13": {"chart_data": 0.50, "structure": 0.30, "text": 0.20},
    # pure prose: fidelity first, then paragraph segmentation
    "p22": {"text": 0.65, "structure": 0.35},
    # two ruled tables embedded in prose
    "p27": {"table": 0.50, "text": 0.25, "structure": 0.25},
    # lists, figures and ordering carry this page
    "p30": {"structure": 0.50, "text": 0.50},
}

OPT_IN = ("furniture", "cell_style")   # reported, never in the composite


def block_text(b):
    return b.get("text") or ""


def is_furniture(b):
    return COARSE.get(b.get("type", ""), "") == "furniture"


# --------------------------------------------------------------------------

def score_text(gold, pred, pairs, um_p, level):
    """Text fidelity, reported two ways.

    `cer` is the headline: edit distance over the whole page's body text, each
    side concatenated in its OWN order. This is the standard document-parsing
    measure. It is segmentation-agnostic — splitting or merging paragraphs does
    not move it, because the characters still land in the same sequence — but it
    is order-sensitive, so a parser that reads a two-column footer in the wrong
    order is penalised here as well as on reading_order_tau.

    That double-charging is deliberate: text in the wrong order really is a
    worse extraction. But it must be decomposable, so `cer_aligned` reports the
    same comparison with predicted blocks re-emitted in GOLD order. Comparing
    the two isolates the cause:

        cer high, cer_aligned low   -> ordering problem, characters are fine
        both high                   -> the parser genuinely lost characters

    Predicted blocks that matched a gold header/footer are excluded from both,
    so a parser is not punished for emitting page furniture.
    """
    # Gold puts table content on the text track (a table block's `text` is its
    # TSV). A parser that emits a table as `structure` with no `text` must get
    # the same credit, so its cells are rendered to TSV here. Without this a
    # correctly-parsed table page scores ~0 on text, which measures the IR
    # convention rather than the parser.
    def ptext(b):
        return block_text(b) or _tsv_of(b)

    furn_pred = {j for i, j, _ in pairs if is_furniture(gold["blocks"][i])}
    g = " ".join(block_text(b) for b in gold["blocks"]
                 if not is_furniture(b) and block_text(b))
    p = " ".join(ptext(b) for j, b in enumerate(pred["blocks"])
                 if j not in furn_pred and ptext(b))
    c, w = M.cer(g, p, level), M.wer(g, p, level)

    matched = {i: j for i, j, _ in pairs}
    parts = [ptext(pred["blocks"][matched[i]])
             for i, b in enumerate(gold["blocks"])
             if not is_furniture(b) and block_text(b) and i in matched]
    parts += [ptext(pred["blocks"][j]) for j in um_p
              if j not in furn_pred and ptext(pred["blocks"][j])]
    c_aligned = M.cer(g, " ".join(x for x in parts if x), level)

    body_pairs = [(i, j, s) for i, j, s in pairs
                  if not is_furniture(gold["blocks"][i]) and block_text(gold["blocks"][i])]
    per_block = statistics.fmean([s for _, _, s in body_pairs]) if body_pairs else 0.0
    return {"score": max(0.0, 1.0 - min(1.0, c)),
            "cer": c, "wer": w, "cer_aligned": c_aligned,
            "order_penalty": max(0.0, c - c_aligned),
            "block_similarity_mean": per_block,
            "gold_chars": len(normalize(g, level)), "pred_chars": len(normalize(p, level))}


def score_structure(gold, pred, pairs, unmatched_g, unmatched_p):
    gold_scored = [i for i, b in enumerate(gold["blocks"]) if not is_furniture(b)]
    pred_furn = {j for i, j, _ in pairs if is_furniture(gold["blocks"][i])}
    pred_scored = [j for j in range(len(pred["blocks"])) if j not in pred_furn]

    tp = sum(1 for i, _, _ in pairs if i in set(gold_scored))
    prec = tp / len(pred_scored) if pred_scored else (1.0 if not gold_scored else 0.0)
    rec = tp / len(gold_scored) if gold_scored else 1.0
    det_f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    strict = coarse = 0
    body_pairs = [(i, j, s) for i, j, s in pairs if i in set(gold_scored)]
    for i, j, _ in body_pairs:
        gt, pt = gold["blocks"][i].get("type"), pred["blocks"][j].get("type")
        strict += gt == pt
        coarse += COARSE.get(gt, gt) == COARSE.get(pt, pt)
    n = len(body_pairs)
    strict_acc = strict / n if n else 0.0
    coarse_acc = coarse / n if n else 0.0
    tau = M.reading_order_tau(body_pairs)

    return {"score": statistics.fmean([det_f1, coarse_acc, tau]),
            "block_detection_f1": det_f1,
            "block_precision": prec, "block_recall": rec,
            "type_accuracy_strict": strict_acc, "type_accuracy_coarse": coarse_acc,
            "reading_order_tau": tau,
            "missed_blocks": [gold["blocks"][i]["id"] for i in unmatched_g
                              if not is_furniture(gold["blocks"][i])],
            "spurious_blocks": len([j for j in unmatched_p if j not in pred_furn])}


def score_tables(gold, pred, level):
    g_tabs = [b for b in gold["blocks"] if b["type"] == "table"]
    p_tabs = [b for b in pred["blocks"] if b.get("type") == "table" and b.get("structure")]
    if not g_tabs:
        return None
    if not p_tabs:
        return {"score": 0.0, "n_gold": len(g_tabs), "n_pred": 0,
                "note": "parser emitted no table structures"}

    # Pair gold tables to predicted tables by TSV similarity.
    pairs, _, _ = M.align_by_similarity([b.get("text", "") for b in g_tabs],
                                        [b.get("text") or _tsv_of(b) for b in p_tabs],
                                        threshold=0.0, level=level)
    per = []
    for gi, pj, _ in pairs:
        gs, ps = g_tabs[gi]["structure"], p_tabs[pj]["structure"]
        ps, inferred = M.infer_headers(ps, gs.get("header_rows", 0))
        best, best_variant = None, None
        for name, variant in M.ambiguity_variants(gs):
            r = M.grits(variant, ps, level)
            h = M.header_span_f1(variant, ps, level)
            combined = 0.5 * r["con"] + 0.25 * r["top"] + 0.25 * h["f1"]
            if best is None or combined > best["combined"]:
                best = {"combined": combined, "grits_con": r["con"], "grits_top": r["top"],
                        "header_f1": h["f1"], "n_gold_cells": r["n_gold_cells"],
                        "n_pred_cells": r["n_pred_cells"]}
                best_variant = name
        best["variant_used"] = best_variant
        best["header_inferred"] = inferred
        best["cell_bag_f1"] = M.cell_bag_f1(gs, ps, level)["f1"]
        best["shape_match"] = M.shape_match(gs, ps)
        best["gold_shape"] = [gs["n_rows"], gs["n_cols"]]
        best["pred_shape"] = [ps.get("n_rows"), ps.get("n_cols")]
        per.append(best)

    missing = len(g_tabs) - len(per)
    score = (sum(t["combined"] for t in per) / len(g_tabs)) if g_tabs else 0.0
    return {"score": score, "n_gold": len(g_tabs), "n_pred": len(p_tabs),
            "unmatched_gold_tables": missing, "tables": per}


def _tsv_of(b):
    st = b.get("structure") or {}
    if not st.get("cells"):
        return ""
    R, C = st.get("n_rows", 0), st.get("n_cols", 0)
    grid = [["" for _ in range(C)] for _ in range(R)]
    for c in st["cells"]:
        if c["row"] < R and c["col"] < C:
            grid[c["row"]][c["col"]] = c.get("text", "")
    return "\n".join("\t".join(r) for r in grid)


def score_chart(gold, pred):
    g_ch = [b for b in gold["blocks"] if b["type"] == "chart"]
    if not g_ch:
        return None
    gc = g_ch[0]["chart"]
    p_ch = [b for b in pred["blocks"] if b.get("type") == "chart" and b.get("chart")]
    if not p_ch:
        return {"score": 0.0, "labels": {"f1": 0.0, "recall": 0.0, "precision": 0.0},
                "note": "parser emitted no chart payload"}
    pc = p_ch[0]["chart"]

    lab = M.chart_labels_prf(gc.get("data_labels", []), pc.get("data_labels", []))
    g_marks, p_marks = gc.get("marks", {}), pc.get("marks", {}) or {}
    cnt = M.count_accuracy(g_marks.get("n", 0), p_marks.get("n", 0) or 0)
    hist = M.histogram_similarity(g_marks.get("by_class", {}), p_marks.get("by_class", {}) or {})
    axes_hit = 0.0
    gx = (gc.get("axes", {}).get("x", {}) or {}).get("label", "")
    px = (pc.get("axes", {}).get("x", {}) or {}).get("label", "")
    gy = (gc.get("axes", {}).get("y", {}) or {}).get("label", "")
    py = (pc.get("axes", {}).get("y", {}) or {}).get("label", "")
    axes_hit = statistics.fmean([M.similarity(gx, px), M.similarity(gy, py)])

    return {"score": 0.55 * lab["f1"] + 0.15 * cnt + 0.15 * hist + 0.15 * axes_hit,
            "labels": lab, "mark_count_accuracy": cnt,
            "gold_marks": g_marks.get("n"), "pred_marks": p_marks.get("n"),
            "class_histogram_similarity": hist, "axis_label_similarity": axes_hit}


def score_furniture(gold, pred, pairs):
    g_f = [i for i, b in enumerate(gold["blocks"]) if is_furniture(b)]
    if not g_f:
        return None
    hit = sum(1 for i, _, _ in pairs if i in set(g_f))
    return {"score": hit / len(g_f), "gold": len(g_f), "found": hit}


# --------------------------------------------------------------------------

def align_blocks(gold, pred, level):
    """Two-stage block alignment.

    Text-bearing blocks are matched by optimal assignment on text similarity.
    Text-less blocks (figures, charts) carry no text to match on, so matching
    them by a placeholder string would make them interchangeable and let an
    arbitrary assignment scramble the reading-order measurement. They are
    instead paired in document order within their coarse type.
    """
    gb, pb = gold["blocks"], pred["blocks"]

    def ptext(b):
        return block_text(b) or _tsv_of(b)

    gi = [i for i, b in enumerate(gb) if block_text(b)]
    pj = [j for j, b in enumerate(pb) if ptext(b)]
    tp, um_gi, um_pj = M.align_by_similarity([block_text(gb[i]) for i in gi],
                                             [ptext(pb[j]) for j in pj], level=level)
    pairs = [(gi[a], pj[b], s) for a, b, s in tp]
    unmatched_g = [gi[a] for a in um_gi]
    unmatched_p = [pj[b] for b in um_pj]

    from collections import defaultdict
    buckets = defaultdict(list)
    for j, b in enumerate(pb):
        if not ptext(b):
            buckets[COARSE.get(b.get("type"), "?")].append(j)
    for i, b in enumerate(gb):
        if block_text(b):
            continue
        k = COARSE.get(b["type"], "?")
        if buckets[k]:
            pairs.append((i, buckets[k].pop(0), 1.0))
        else:
            unmatched_g.append(i)
    for leftover in buckets.values():
        unmatched_p.extend(leftover)

    pairs.sort(key=lambda x: x[0])
    return pairs, sorted(unmatched_g), sorted(unmatched_p)


def score_page(gold_path, pred_path, level):
    gold = json.loads(Path(gold_path).read_text())
    pred = json.loads(Path(pred_path).read_text())
    if pred.get("page_id") != gold["page_id"]:
        raise SystemExit(f"page_id mismatch: {pred.get('page_id')} vs {gold['page_id']}")

    pairs, um_g, um_p = align_blocks(gold, pred, level)

    tracks = {
        "text": score_text(gold, pred, pairs, um_p, level),
        "structure": score_structure(gold, pred, pairs, um_g, um_p),
        "table": score_tables(gold, pred, level),
        "chart_data": score_chart(gold, pred),
        "furniture": score_furniture(gold, pred, pairs),
    }
    tracks = {k: v for k, v in tracks.items() if v is not None}

    weights = PAGE_WEIGHTS[gold["page_id"]]
    total = sum(w for t, w in weights.items() if t in tracks)
    composite = (sum(tracks[t]["score"] * w for t, w in weights.items() if t in tracks) / total
                 if total else 0.0)

    return {"page_id": gold["page_id"], "level": level,
            "composite": composite, "weights": weights,
            "tracks": tracks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--level", default="L1", choices=("L0", "L1", "L2"))
    ap.add_argument("--json", default=None, help="write full results here")
    a = ap.parse_args()

    run = Path(a.run_dir)
    pages = sorted(p for p in run.glob("*.json"))
    if not pages:
        sys.exit(f"no page files in {run}")

    results, name = [], run.name
    for p in pages:
        gp = GOLD / p.name
        if not gp.exists():
            print(f"  skip {p.name}: no gold", file=sys.stderr)
            continue
        results.append(score_page(gp, p, a.level))

    all_tracks = ["text", "structure", "table", "chart_data", "furniture"]
    print(f"\nparser: {name}    normalisation: {a.level}\n")
    head = f"{'page':6s} {'composite':>9s} " + " ".join(f"{t:>11s}" for t in all_tracks)
    print(head)
    print("-" * len(head))
    for r in results:
        row = f"{r['page_id']:6s} {r['composite']:9.3f} "
        for t in all_tracks:
            row += f"{r['tracks'][t]['score']:11.3f} " if t in r["tracks"] else f"{'-':>11s} "
        print(row)
    print("-" * len(head))
    overall = statistics.fmean([r["composite"] for r in results]) if results else 0.0
    row = f"{'MEAN':6s} {overall:9.3f} "
    for t in all_tracks:
        vals = [r["tracks"][t]["score"] for r in results if t in r["tracks"]]
        row += f"{statistics.fmean(vals):11.3f} " if vals else f"{'-':>11s} "
    print(row)

    out = {"parser": name, "level": a.level, "overall": overall, "pages": results}
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        print(f"\nwrote {a.json}")
    return out


if __name__ == "__main__":
    main()
