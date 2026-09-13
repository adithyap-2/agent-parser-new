# Gold Standard Schema v1.0

One JSON file per page, in `gold/pages/<page_id>.json`. The schema is
**parser-agnostic**: it describes what is on the page, not what any particular
tool emits. Scoring adapters are responsible for mapping parser output onto it.

## Guiding principles

1. **Verbatim gold, normalizing scorer.** Gold `text` reproduces the page
   exactly — smart quotes, superscripts, en dashes and all. Normalization
   (case, quote folding, whitespace, unicode) belongs in the scorer so that a
   single gold can serve strict and lenient metrics.
2. **Structure is the judgement, characters are not.** The source is
   digital-born, so the character content of each page is objective and is
   seeded from the PDF text layer. Everything above the character level —
   block boundaries, block types, table cell topology, reading order — was
   assigned by hand against the 200 dpi render.
3. **Separable tracks.** A parser that cannot see images should not be scored
   to zero on a page whose chart is a bitmap. Each block declares which
   scoring tracks it participates in.

## Top-level object

```jsonc
{
  "schema_version": "1.0",
  "page_id": "p04",
  "source": {
    "pdf": "parser-benchmark.pdf",       // original 30-page deck
    "page_number": 4,                     // 1-based page in that deck
    "page_pdf": "benchmark/pages/p04_exec_summary_table.pdf",
    "render": "benchmark/renders/p04_exec_summary_table.png"
  },
  "page": {
    "width_pt": 792, "height_pt": 612,
    "orientation": "landscape",
    "origin": "digital"                   // digital | scanned
  },
  "annotation": {
    "method": "text-layer seed + visual verification against 200dpi render",
    "verified": true,
    "notes": "..."                        // page-specific caveats
  },
  "content_profile": ["table", "prose"],  // what this page is in the benchmark for
  "blocks": [ /* see below */ ],
  "reading_order": ["p04.b01", "p04.b02", ...],
  "tracks": { /* see below */ }
}
```

## Block object

Every block:

```jsonc
{
  "id": "p04.b03",
  "type": "table",
  "reading_order": 3,          // 1-based; matches index in reading_order[]
  "bbox": [18.0, 64.2, 770.5, 484.9],   // PDF points, origin top-left, [x0,y0,x1,y1]
  "region": "body",            // body | header | footer | marginal
  "tracks": ["structure", "table"],
  "text": "..."                // present on all text-bearing block types
}
```

Optional block fields:

| field | on | meaning |
|-------|----|---------|
| `level` | `heading` | 1–3 |
| `bold_spans` | any text block | the exact bold runs inside it, in order. Records run-in labels such as `"Holdings:"` that a parser may (reasonably) split on |
| `underlined` | any text block | set when a heading is marked by a rule rather than by weight |
| `caption_for` | `caption` | id of the block the caption belongs to |

### `type` vocabulary

| type | meaning |
|------|---------|
| `title` | The page's dominant title |
| `heading` | Section heading; carries `level` (1–3) |
| `banner` | Coloured section bar acting as a sub-heading |
| `paragraph` | Running prose |
| `list` | A bulleted/numbered list; carries `items[]` and `marker_style` |
| `table` | Carries `structure` |
| `chart` | A data graphic; carries `chart` |
| `figure` | Non-data image; carries `figure` |
| `caption` | Caption bound to a figure/table/chart via `caption_for` |
| `footnote` | Footnote / source note tied to page content |
| `header` / `footer` | Running page furniture |

### Type-specific payloads

**`list`**
```jsonc
{
  "type": "list", "marker_style": "bullet",   // bullet | dash | decimal | alpha
  "items": [
    { "text": "The number of funds in the universe from which to select peers",
      "level": 0, "marker_raw": "" }
  ]
}
```
`marker_raw` records the glyph actually used (here a Symbol-font private-use
bullet). Item `text` **excludes** the marker — markers are presentation, not
content. `text` on the block is the items joined by `\n`.

**`table`**
```jsonc
{
  "type": "table",
  "structure": {
    "n_rows": 41, "n_cols": 15,
    "header_rows": 2,
    "cells": [
      { "row": 0, "col": 2, "rowspan": 1, "colspan": 2,
        "text": "Net Advisory²", "is_header": true }
    ]
  }
}
```
- Grid coordinates are **logical**, after expanding spans: a cell with
  `colspan:2` at `col:2` occupies logical columns 2 and 3, and no other cell
  declares those. The validator proves every grid position is covered exactly
  once.
- Empty cells are included with `"text": ""` so the grid is complete. This
  matters: a parser that drops empty cells shifts every column after it.
- `text` is the cell's verbatim content, spaces collapsed.
- A cell may carry `"color"` when the page colours it meaningfully (page 4 uses
  colour to encode quartile ranking). Scored only on the `cell_style` track.
- The block's `text` is a TSV rendering (rows by `\n`, cells by `\t`), provided
  as a convenience for text-level metrics. It is stored unnormalised so the tab
  delimiters survive.
- `structure.ambiguities` records header shapes where a second reading is
  genuinely defensible, so a scorer can accept either:

```jsonc
"ambiguities": [{
  "cells": ["row0/col0", "row0/col1", "row0/col2"],
  "encoded_as": "empty header cells; labels live in row1",
  "accepted_alternative": "row1 labels raised to row0 with rowspan=2",
  "reason": "table top is ragged — the group-header band has no border above columns 0-2"
}]
```

**`chart`**
```jsonc
{
  "type": "chart",
  "chart": {
    "chart_type": "bubble",
    "rasterized": true,          // true => recoverable only by vision/OCR
    "raster": { "xref": 294, "px": [3132, 1754], "dpi_equiv": 300 },
    "title": "Total Net Expense Percentile**",
    "axes": {
      "x": { "label": "...", "ticks": ["0%","50%","100%"], "direction": "left-to-right" },
      "y": { "label": "...", "ticks": ["0%","50%","100%"], "direction": "top-to-bottom",
             "note": "axis is inverted; 0% is at the top" }
    },
    "encodings": { "x": "...", "y": "...", "size": "...", "color": "..." },
    "legend": { "block": "p13.b08",
                "classes": [ {"class": "green", "hex": "#008000"} ] },
    "calibration": { "plot_box_px": [377,220,2690,1673],
                     "gridlines_px": { "rows": [...], "cols": [...] },
                     "method": "0/50/100% gridlines located in the bitmap" },
    "marks": {
      "n": 53,
      "method": "per-colour-class segmentation (tools/detect_bubbles.py)",
      "by_class": { "green": 15, "gold": 16 },
      "bubbles": [ { "x_pct": 22.2, "y_pct": 11.1, "r_px": 76.8,
                     "color_class": "green", "size_band": "large",
                     "clipped": false } ]
    },
    "data_labels": [ "AAAA", "BBBB" ],
    "scoring_note": "..."
  }
}
```

Two rules make this honest rather than fabricated:

- **Marks are measured, not estimated.** Positions come from segmenting the
  bitmap and calibrating on gridlines the detector locates, so they are
  reproducible. `clipped: true` flags marks cut off by the plot frame, whose
  centroid is biased inward and which should be scored with tolerance.
- **Labels are not bound to marks.** Many labels reach their mark through a
  leader line that crosses other marks, and some marks are unlabelled. Gold
  gives the label set and the mark set separately rather than inventing a
  binding. `data_labels` is scored as a set; that is the primary `chart_data`
  signal.

**`figure`**
```jsonc
{ "type": "figure",
  "figure": { "kind": "icon", "raster": {"xref": 638, "px": [107, 91]},
              "description": "Magnifying glass over a document",
              "contains_text": false } }
```

## Tracks

Tracks let one gold file serve several metrics without unfairly penalising
parsers of different classes.

| track | scored over | purpose |
|-------|-------------|---------|
| `text` | blocks with `text`, `region: body` | character/word accuracy of extractable prose |
| `structure` | all blocks | block type + reading-order fidelity |
| `table` | `table` blocks | cell topology (TEDS / GriTS / cell F1) |
| `chart_data` | `chart` blocks | vision-only: can the parser read a bitmap chart |
| `furniture` | `header`/`footer` blocks | opt-in; most parsers legitimately drop these |
| `cell_style` | `table` cells with `color` | opt-in; colour that carries meaning |

The page-level `tracks` object records which apply and any per-track caveats:

```jsonc
"tracks": {
  "text":       { "applicable": true,  "n_blocks": 12 },
  "structure":  { "applicable": true,  "n_blocks": 14 },
  "table":      { "applicable": true,  "n_tables": 1 },
  "chart_data": { "applicable": false },
  "furniture":  { "applicable": true,  "n_blocks": 2 }
}
```

## Rules for `text`

- Verbatim characters; no case folding, no quote folding.
- Runs of whitespace collapse to a single space; leading/trailing stripped.
- Soft line breaks **within** a paragraph are joined with a single space —
  line wrapping is layout, not content.
- Hard breaks that are semantically real (list items, table rows, address
  lines) are preserved as `\n`.
- List markers and table rules are excluded.
- Footnote reference marks that are real characters in the text layer
  (`²`, `*`, `**`) are **kept**, attached to the word they follow.

## Conventions

- `bbox` is `[x0, y0, x1, y1]` in PDF points with **origin at page top-left**
  (PyMuPDF convention), not PDF-native bottom-left.
- `id` is `<page_id>.b<NN>`, numbered in reading order, zero-padded to 2.
- `reading_order` is a single linear sequence per page. Where the visual layout
  is genuinely two-column or side-by-side, the chosen order is documented in
  `annotation.notes` — these are the cases that discriminate parsers most, so
  the rationale is recorded rather than left implicit.
