# Benchmark Specification

Scores a parser against [the gold standard](../gold/README.md). Five pages,
five tracks, one composite per page.

```bash
.venv/bin/python bench/synth.py                    # reference/synthetic runs
.venv/bin/python bench/score.py runs/<parser>/     # score a run
.venv/bin/python bench/calibrate.py                # prove the metrics still work
```

## 1. Parser output format (IR)

One JSON file per page, named `<page_id>.json`, under `runs/<parser>/`.

```jsonc
{
  "page_id": "p04",
  "parser": { "name": "pymupdf", "version": "1.28.2" },
  "blocks": [                       // in the parser's reading order
    { "type": "paragraph", "text": "...", "bbox": [x0,y0,x1,y1] },
    { "type": "table", "structure": { "n_rows": 29, "n_cols": 14,
        "header_rows": 2,
        "cells": [ {"row":0,"col":3,"rowspan":1,"colspan":2,
                    "text":"Net Advisory²","is_header":true} ] } },
    { "type": "chart", "chart": { "data_labels": ["AAAA"],
        "marks": { "n": 53, "by_class": {"green": 15} },
        "axes": { "x": {"label": "..."}, "y": {"label": "..."} } } }
  ]
}
```

Only `type` and `text` are required. A parser that emits nothing but text still
scores on the `text` track — it simply scores 0 on `table` and `chart_data`.
`type` may use any vocabulary; unknown names fall back to coarse matching.

## 2. Normalisation

Gold is verbatim, so every comparison decision lives in the scorer. Results are
meaningless without stating the level, so `score.py` always prints it.

| level | does | use for |
|-------|------|---------|
| `L0` | NFC + whitespace collapse | strictest; quotes, superscripts, case all count |
| `L1` **(default)** | + fold quotes/dashes to ASCII, expand ligatures, superscript digits → ASCII | headline. Stops penalising `'` vs `’`, a font-encoding artefact rather than a reading error |
| `L2` | + casefold | comparing parsers that normalise heading case |

Table cells additionally treat an all-dash string (`-----`, the financial
"no value" filler) as empty, so the table score measures structure rather than
typographic filler.

## 3. Tracks and metrics

| track | score = | also reported |
|-------|---------|---------------|
| `text` | `1 - CER` | `wer`, `cer_aligned`, `order_penalty`, `block_similarity_mean` |
| `structure` | mean of detection F1, coarse type accuracy, reading-order τ | strict type accuracy, precision/recall, missed block ids |
| `table` | `0.5·GriTS-Con + 0.25·GriTS-Top + 0.25·header_F1` | `cell_bag_f1`, `shape_match`, `variant_used` |
| `chart_data` | `0.55·label_F1 + 0.15·count + 0.15·class_hist + 0.15·axis_labels` | precision/recall, missed and spurious labels |
| `furniture` | fraction of header/footer blocks found | opt-in, never in the composite |

### text — the order question

`cer` concatenates each side's body text **in its own order**. That is the
standard document-parsing measure: segmentation-agnostic (splitting or merging
paragraphs doesn't move it) but order-sensitive.

So a reading-order failure is charged twice — once here, once on
`reading_order_tau`. That is deliberate: text in the wrong order really is a
worse extraction. But it must be *decomposable*, so `cer_aligned` repeats the
comparison with predicted blocks re-emitted in gold order:

| | meaning |
|---|---|
| `cer` high, `cer_aligned` ≈ 0 | ordering problem; characters are fine |
| both high | the parser genuinely lost characters |

`order_penalty = cer - cer_aligned` names the gap directly.

**Caveat.** `cer_aligned` reconstructs predicted text in gold order using the
block matching, so it is only trustworthy when that matching is good. A parser
that segments very differently from gold (many spurious or missed blocks) can
score *worse* on `cer_aligned` than on `cer` — PyMuPDF does exactly this on
p27, where it splits the tables differently and scores `cer` 0.097 against
`cer_aligned` 0.566. `order_penalty` clamps at 0, correctly reporting "no
ordering problem detected", but read `cer_aligned` alongside
`structure.spurious_blocks` before drawing conclusions from it.

Blocks matching a gold header/footer are removed from both sides, so no parser
is punished for emitting running furniture.

### structure — block matching

Two-stage, and the staging matters. Text-bearing blocks are matched by
**Hungarian assignment** on text similarity, not greedily — a greedy match
depends on block order, and order is a thing we measure, so it must not
contaminate matching. Text-less blocks (figures, charts) have no text to match
on; pairing them by a placeholder would make them interchangeable and let an
arbitrary assignment scramble the order measurement, so they are paired in
document order within their coarse type.

### table — GriTS

`grits()` is a **two-pass approximation**: rows are aligned by Needleman-Wunsch
on row strings, then columns, then cells are compared at aligned positions.
Optimal 2D grid alignment is intractable; this is stable and degrades sensibly,
which is what a benchmark needs. Both scores use the GriTS normaliser
`2·S / (|G| + |P|)`, so inventing cells costs as much as missing them.

`cell_bag_f1` is the order-free floor — a multiset comparison of cell strings
that ignores geometry entirely. It separates *"read the values but mangled the
layout"* from *"lost the values"*.

**Declared ambiguities are honoured.** Page 4's ragged header has two
defensible readings; the scorer tries both and takes the better, reporting
`variant_used`. A parser is not penalised for choosing the one gold didn't.

### chart_data — why labels dominate

Label set F1 carries 55% because it is the one chart signal that is both
objective and fully recoverable. Mark count is tolerance-banded (±10%, decaying
to 0 at ±30%) because the gold's own count is a measurement — overlapping
same-colour bubbles can merge — and exact-match scoring there would measure the
gold's noise floor rather than the parser.

## 4. Per-page specification

### p04 — wide hierarchical table
`table 0.65 · structure 0.20 · text 0.15`

Tests 14 columns under a two-level header with `colspan` 2 and 3, labels
wrapped over two lines, and 107 cells reading `N/A`.

*Failure modes it detects:* dropping no-value cells and re-packing (column
shift → `grits_con` collapses while `grits_top` holds); flattening merged
header cells (`grits_top` and `header_f1` fall, content holds); not emitting
table structure at all (score 0).

*Declared ambiguity:* row0/col0-2 empty vs `rowspan=2` — both accepted.

### p13 — rasterised chart
`chart_data 0.50 · structure 0.30 · text 0.20`

The plot is one bitmap: axis titles, tick labels, ~52 data labels and all
leader lines are pixels only. **A text extractor scores 1.000 on `text` here
and 0.000 on `chart_data`** — that separation is the page's purpose. The
30% on structure carries the second trap: the two-column footer interleaves
vertically, so naive top-to-bottom ordering is punished.

*Reference:* `y_sorted` scores 0.880 on this page and 1.000 everywhere else.

### p22 — dense prose
`text 0.65 · structure 0.35`

~1,560 words of justified 7 pt text. Tests character fidelity first, paragraph
segmentation second — including the run-in label `Characteristics:` that starts
mid-paragraph and invites a spurious split.

*Reference:* `merged_paragraphs` scores 0.919 here — text 1.000, structure
0.952 — showing the two are cleanly separated.

### p27 — prose plus ruled tables
`table 0.50 · structure 0.25 · text 0.25`

Two tables with a two-level header where `Fund` is `rowspan=2` and
`Std. Deviation` spans one column. Sub-columns inside the ruled groups are
unruled and must be inferred.

### p30 — lists, figures, ordering
`structure 0.50 · text 0.50`

Two bullet glyphs (U+F0B7 with no trailing space; U+2022), markers excluded
from item text, four figures of which three are icons, and icon → heading →
list ordering within each panel.

## 5. Calibration

`calibrate.py` runs 26 assertions against ten synthetic degradations. Each
assertion states a property the benchmark *claims*; if one fails, the metric is
wrong, not the parser. Current reference matrix (L1):

| degradation | overall | text | structure | table | chart_data |
|---|---|---|---|---|---|
| `perfect` | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| `alt_header` | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| `noisy_text` (2% chars) | 0.993 | 0.980 | 1.000 | 1.000 | 1.000 |
| `merged_paragraphs` | 0.983 | 1.000 | 0.952 | 1.000 | 1.000 |
| `half_chart_labels` | 0.982 | 1.000 | 1.000 | 1.000 | 0.817 |
| `flat_header` | 0.980 | 1.000 | 1.000 | 0.911 | 1.000 |
| `dropped_na_cells` | 0.979 | 1.000 | 1.000 | 0.918 | 1.000 |
| `y_sorted` | 0.975 | 0.902 | 0.983 | 1.000 | 1.000 |
| `no_chart_labels` | 0.900 | 1.000 | 1.000 | 1.000 | 0.000 |
| `text_only` | 0.600 | 1.000 | 0.778 | 0.000 | 0.000 |

Read the rows, not the overall column: every degradation moves its own track
and leaves the others alone. `text_only` is the useful baseline — it is roughly
what a plain text extractor produces, and any real parser should beat 0.600.

## 6. Known limits

1. **`grits` is an approximation**, not optimal 2D alignment (see §3).
2. **Composite weights are a judgement.** They are declared per page in
   `PAGE_WEIGHTS` in `score.py` rather than hidden in an average; change them
   there if your priorities differ, and say so when reporting.
3. **Overall mean weights every page equally**, so the chart page carries 20%
   of a five-page benchmark. With n=5, prefer the per-track and per-page
   breakdown over the single number.
4. **Block typing is scored coarsely by default** because parser vocabularies
   differ. `type_accuracy_strict` is reported but not scored.
5. **No positional scoring.** Bounding-box IoU is not measured; blocks are
   matched by text. A parser with perfect text and nonsense geometry scores
   well.
