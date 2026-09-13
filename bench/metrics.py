"""Metric implementations for the parser benchmark.

Every metric returns a float in [0, 1] where 1 is perfect, or a dict of such
floats, so page and track scores compose by weighted mean without special cases.
Error-style quantities (CER, WER) are reported both raw and as `1 - min(1, err)`
accuracy so they compose the same way.
"""
import math

import numpy as np
from rapidfuzz.distance import Levenshtein
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment
from scipy.stats import kendalltau

from normalize import normalize, tokens, norm_cell


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------

def cer(gold: str, pred: str, level="L1") -> float:
    g, p = normalize(gold, level), normalize(pred, level)
    if not g:
        return 0.0 if not p else 1.0
    return Levenshtein.distance(g, p) / len(g)


def wer(gold: str, pred: str, level="L1") -> float:
    g, p = tokens(gold, level), tokens(pred, level)
    if not g:
        return 0.0 if not p else 1.0
    return Levenshtein.distance(g, p) / len(g)


def similarity(a: str, b: str, level="L1") -> float:
    a, b = normalize(a, level), normalize(b, level)
    if not a and not b:
        return 1.0
    return fuzz.ratio(a, b) / 100.0


# --------------------------------------------------------------------------
# sets
# --------------------------------------------------------------------------

def set_prf(gold, pred) -> dict:
    g, p = set(gold), set(pred)
    tp = len(g & p)
    prec = tp / len(p) if p else (1.0 if not g else 0.0)
    rec = tp / len(g) if g else (1.0 if not p else 0.0)
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1,
            "tp": tp, "fp": len(p - g), "fn": len(g - p)}


def histogram_similarity(gold: dict, pred: dict) -> float:
    """1 - total variation distance between two normalised histograms."""
    keys = set(gold) | set(pred)
    gs, ps = sum(gold.values()), sum(pred.values())
    if not gs and not ps:
        return 1.0
    if not gs or not ps:
        return 0.0
    tv = 0.5 * sum(abs(gold.get(k, 0) / gs - pred.get(k, 0) / ps) for k in keys)
    return 1.0 - tv


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------

def align_by_similarity(gold_texts, pred_texts, threshold=0.55, level="L1"):
    """Optimal 1:1 assignment of predicted blocks to gold blocks.

    Uses Hungarian assignment on text similarity rather than greedy matching, so
    the result does not depend on block order — important because reading order
    is itself something we measure and must not contaminate block matching.
    Pairs below `threshold` are discarded as non-matches.
    """
    if not gold_texts or not pred_texts:
        return [], list(range(len(gold_texts))), list(range(len(pred_texts)))
    S = np.zeros((len(gold_texts), len(pred_texts)))
    for i, g in enumerate(gold_texts):
        for j, p in enumerate(pred_texts):
            S[i, j] = similarity(g, p, level)
    rows, cols = linear_sum_assignment(-S)
    pairs = [(int(i), int(j), float(S[i, j])) for i, j in zip(rows, cols)
             if S[i, j] >= threshold]
    matched_g = {i for i, _, _ in pairs}
    matched_p = {j for _, j, _ in pairs}
    return (pairs,
            [i for i in range(len(gold_texts)) if i not in matched_g],
            [j for j in range(len(pred_texts)) if j not in matched_p])


def align_sequences(a, b, sim, min_sim=0.35):
    """Needleman-Wunsch alignment maximising total similarity, gap cost 0.

    Returns matched (i, j) index pairs in order. Used to line up table rows and
    columns when the predicted grid has extra or missing ones.
    """
    n, m = len(a), len(b)
    D = np.zeros((n + 1, m + 1))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = sim(a[i - 1], b[j - 1])
            D[i, j] = max(D[i - 1, j], D[i, j - 1],
                          D[i - 1, j - 1] + (s if s >= min_sim else -1e-9))
    out, i, j = [], n, m
    while i > 0 and j > 0:
        s = sim(a[i - 1], b[j - 1])
        if s >= min_sim and math.isclose(D[i, j], D[i - 1, j - 1] + s, rel_tol=1e-9, abs_tol=1e-12):
            out.append((i - 1, j - 1)); i -= 1; j -= 1
        elif math.isclose(D[i, j], D[i - 1, j], rel_tol=1e-9, abs_tol=1e-12):
            i -= 1
        else:
            j -= 1
    return out[::-1]


def reading_order_tau(pairs) -> float:
    """Kendall tau-b over matched blocks, rescaled from [-1,1] to [0,1].

    Measures only ORDER, over blocks both sides found. A parser that finds every
    block but emits them in a scrambled sequence scores low here and high on
    text — which is exactly the separation page 13 is built to expose.
    """
    if len(pairs) < 2:
        return 1.0
    g = [i for i, _, _ in pairs]
    p = [j for _, j, _ in pairs]
    tau, _ = kendalltau(g, p)
    if tau is None or (isinstance(tau, float) and math.isnan(tau)):
        return 1.0
    return (float(tau) + 1.0) / 2.0


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------

def expand_grid(structure):
    """Cells -> an R x C array of (text, rowspan, colspan, is_header)."""
    R, C = structure["n_rows"], structure["n_cols"]
    grid = [[("", 1, 1, False)] * C for _ in range(R)]
    grid = [[("", 1, 1, False) for _ in range(C)] for _ in range(R)]
    for c in structure["cells"]:
        rs, cs = c.get("rowspan", 1), c.get("colspan", 1)
        val = (c.get("text", ""), rs, cs, bool(c.get("is_header")))
        for r in range(c["row"], min(c["row"] + rs, R)):
            for k in range(c["col"], min(c["col"] + cs, C)):
                grid[r][k] = val
    return grid


def _row_text(grid, r, level):
    return " | ".join(norm_cell(grid[r][c][0], level) for c in range(len(grid[0])))


def _col_text(grid, c, level):
    return " | ".join(norm_cell(grid[r][c][0], level) for r in range(len(grid)))


def grits(gold_struct, pred_struct, level="L1") -> dict:
    """GriTS-style two-pass grid similarity.

    The optimal 2D grid alignment is intractable, so rows are aligned first
    (Needleman-Wunsch on row strings), then columns, and cells are compared at
    the aligned positions. This is an approximation and is documented as one;
    it is stable and it degrades sensibly, which is what a benchmark needs.

      con  content similarity   (GriTS-Con analogue)
      top  topology similarity  (spans + header flag; GriTS-Top analogue)

    Both use the GriTS normaliser 2*S / (|G| + |P|), so a parser is penalised
    for inventing cells as well as for missing them.
    """
    G, P = expand_grid(gold_struct), expand_grid(pred_struct)
    ng, np_ = len(G) * len(G[0]), len(P) * len(P[0])
    if not ng or not np_:
        return {"con": 0.0, "top": 0.0, "n_gold_cells": ng, "n_pred_cells": np_}

    rmap = align_sequences(range(len(G)), range(len(P)),
                           lambda i, j: fuzz.ratio(_row_text(G, i, level),
                                                   _row_text(P, j, level)) / 100.0)
    cmap = align_sequences(range(len(G[0])), range(len(P[0])),
                           lambda i, j: fuzz.ratio(_col_text(G, i, level),
                                                   _col_text(P, j, level)) / 100.0)

    s_con = s_top = 0.0
    for gr, pr in rmap:
        for gc, pc in cmap:
            gt, grs, gcs, gh = G[gr][gc]
            pt, prs, pcs, ph = P[pr][pc]
            gt, pt = norm_cell(gt, level), norm_cell(pt, level)
            s_con += 1.0 if gt == pt else fuzz.ratio(gt, pt) / 100.0
            s_top += 1.0 if (grs, gcs, gh) == (prs, pcs, ph) else 0.0
    return {"con": 2 * s_con / (ng + np_), "top": 2 * s_top / (ng + np_),
            "n_gold_cells": ng, "n_pred_cells": np_,
            "rows_aligned": len(rmap), "cols_aligned": len(cmap)}


def cell_bag_f1(gold_struct, pred_struct, level="L1") -> dict:
    """Order-free floor: multiset F1 over non-empty cell strings.

    Insensitive to grid geometry entirely, so it separates 'read the values but
    mangled the layout' from 'lost the values'.
    """
    import collections
    g = collections.Counter(norm_cell(c.get("text", ""), level)
                            for c in gold_struct["cells"] if norm_cell(c.get("text", ""), level))
    p = collections.Counter(norm_cell(c.get("text", ""), level)
                            for c in pred_struct["cells"] if norm_cell(c.get("text", ""), level))
    tp = sum((g & p).values())
    gp, pp = sum(g.values()), sum(p.values())
    prec = tp / pp if pp else (1.0 if not gp else 0.0)
    rec = tp / gp if gp else (1.0 if not pp else 0.0)
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1}


def shape_match(gold_struct, pred_struct) -> float:
    return float(gold_struct["n_rows"] == pred_struct.get("n_rows")
                 and gold_struct["n_cols"] == pred_struct.get("n_cols"))


def infer_headers(pred_struct, gold_header_rows):
    """Mark header cells positionally when the parser cannot express the flag.

    Table-recognition models commonly emit HTML using `<td>` throughout, with no
    `<th>` or `<thead>` — MinerU does exactly this. Such a parser can reproduce
    a two-level header perfectly (correct rowspan/colspan) yet score 0 on
    header_f1 and lose points on grits_top, purely because a boolean it has no
    way to emit is False. That measures the output format, not the parser.

    So: if NO predicted cell is flagged as a header, the top N rows are treated
    as the header, where N is the parser's own declared `header_rows` when it
    gives one, and gold's otherwise. The spans themselves are still compared
    normally — only the flag is supplied. Results record `header_inferred`.
    """
    cells = pred_struct.get("cells", [])
    if any(c.get("is_header") for c in cells):
        return pred_struct, False
    n = pred_struct.get("header_rows") or gold_header_rows or 0
    if not n:
        return pred_struct, False
    new = [dict(c, is_header=(c["row"] < n)) for c in cells]
    return dict(pred_struct, cells=new, header_rows=n), True


def header_span_f1(gold_struct, pred_struct, level="L1") -> dict:
    """F1 over header cells as (text, rowspan, colspan) triples.

    Isolates hierarchical-header handling from body accuracy — the specific
    thing pages 4 and 27 are in the benchmark to test.
    """
    def hdr(st):
        return [(norm_cell(c.get("text", ""), level), c.get("rowspan", 1), c.get("colspan", 1))
                for c in st["cells"] if c.get("is_header")]
    import collections
    g, p = collections.Counter(hdr(gold_struct)), collections.Counter(hdr(pred_struct))
    tp = sum((g & p).values())
    gp, pp = sum(g.values()), sum(p.values())
    prec = tp / pp if pp else (1.0 if not gp else 0.0)
    rec = tp / gp if gp else (1.0 if not pp else 0.0)
    return {"precision": prec, "recall": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0}


def ambiguity_variants(structure):
    """Yield the gold grid plus any alternative readings it declares acceptable.

    Page 4's header is genuinely ambiguous (ragged table top). Gold encodes one
    reading and names the other in structure.ambiguities; the scorer must not
    punish a parser for choosing the other. Scores are taken as the max over
    variants and the winning variant is reported.
    """
    yield "as_encoded", structure
    for amb in structure.get("ambiguities", []):
        if "rowspan=2" not in amb.get("accepted_alternative", ""):
            continue
        cols = []
        for ref in amb.get("cells", []):
            try:
                cols.append(int(ref.split("/col")[1]))
            except (IndexError, ValueError):
                pass
        if not cols:
            continue
        cells = [dict(c) for c in structure["cells"]]
        keep = []
        for c in cells:
            if c["row"] == 0 and c["col"] in cols and not c.get("text"):
                continue                       # drop the empty placeholder
            if c["row"] == 1 and c["col"] in cols:
                c = dict(c, row=0, rowspan=2)  # raise the label, span both rows
            keep.append(c)
        yield "rowspan2_alternative", dict(structure, cells=keep)


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------

def chart_labels_prf(gold_labels, pred_labels, level="L2") -> dict:
    g = {normalize(x, level) for x in gold_labels if normalize(x, level)}
    p = {normalize(x, level) for x in pred_labels if normalize(x, level)}
    r = set_prf(g, p)
    r["missed_examples"] = sorted(g - p)[:8]
    r["spurious_examples"] = sorted(p - g)[:8]
    return r


def count_accuracy(gold_n: int, pred_n: int, tol_frac=0.10) -> float:
    """1.0 inside a tolerance band, decaying linearly to 0 at 3x the band.

    Bubble counts are a measurement (overlapping same-colour marks can merge),
    so exact-match scoring here would measure the gold's noise floor, not the
    parser.
    """
    if gold_n == 0:
        return 1.0 if pred_n == 0 else 0.0
    err = abs(pred_n - gold_n) / gold_n
    if err <= tol_frac:
        return 1.0
    return max(0.0, 1.0 - (err - tol_frac) / (2 * tol_frac))
