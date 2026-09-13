# Gold Standard

Hand-authored ground truth for the 5-page parser benchmark. One JSON file per
page in `pages/`, conforming to [SCHEMA.md](SCHEMA.md).

## How it was made

The source deck is **digital-born**, which splits the problem cleanly:

- **Character content is objective.** It is taken from the PDF text layer, so
  gold cannot contain typos and cannot silently omit a word. `validate_gold.py`
  proves this by comparing character multisets in both directions.
- **Structure is a judgement.** Block boundaries, block types, table cell
  topology and reading order were assigned by hand against 200 dpi renders, and
  table grids were read off the pages' own vector rules rather than guessed
  from text positions. Every non-obvious call is recorded in
  `annotation.notes` on the page it affects.

Gold is **generated, not edited**. To change it, edit the builder in `tools/`
and rebuild — never hand-edit the JSON.

```bash
.venv/bin/python tools/build_all.py        # rebuild all 5 pages + validate
.venv/bin/python tools/validate_gold.py    # validate only
.venv/bin/python tools/test_validate_gold.py   # negative tests for the validator
```

## What's in it

| page | src | orient. | blocks | words | tables | tracks |
|------|-----|---------|--------|-------|--------|--------|
| `p04` | 4 | landscape | 6 | 25 | 29×14, 400 cells | text, structure, table, furniture, cell_style |
| `p13` | 13 | landscape | 9 | 144 | — | text, structure, chart_data, furniture |
| `p22` | 22 | landscape | 12 | 1562 | — | text, structure, furniture |
| `p27` | 27 | portrait | 12 | 122 | 15×8 + 14×8, 222 cells | text, structure, table, furniture |
| `p30` | 30 | portrait | 17 | 445 | — | text, structure, furniture |

Totals: 56 blocks, 622 table cells, ~2,300 words of prose, 1 chart, 4 figures.

## The traps each page sets

Everything below is a deliberate discriminator, not an accident of the source.

**p04 — wide hierarchical table.** 14 columns under a two-level header with
`colspan` 2 and 3. The table top is **ragged**: the group-header band exists
only over columns 3–13, so `Group` / `Fund` / `Avg. AUM ($M)` are boxed in the
lower band only. Gold encodes row 0 columns 0–2 as *empty* cells and declares
the `rowspan=2` reading as an accepted alternative in `structure.ambiguities`.
Header labels wrap over two lines and must be rejoined. Unavailable values are
the literal string `N/A` and must be reproduced, not dropped. Cell colour
encodes quartile ranking (`cell_style`).

**p13 — rasterised chart.** The whole plot area is one 3132×1754 bitmap: both
axis titles, all tick labels, ~52 data labels and every leader line are pixels
only. The text layer holds just the heading, banner, KEY legend, three
footnotes and the page number. **A text-extraction parser can score near-full
marks on `text` while recovering nothing from the chart** — that separation is
the point. Below the chart the page is two side-by-side groups (left
footnotes, right legend) that interleave vertically; gold orders them
column-wise, so a strict top-to-bottom parser fails *reading order*, not text.

**p22 — dense prose.** ~1,560 words of justified 7 pt text with no layout
scaffolding. Paragraph breaks come from the ~14 pt inter-paragraph gap vs ~8 pt
line leading. Seven bold run-in labels introduce topics; six open a paragraph,
but **`Characteristics:` starts mid-line inside the `Holdings:` paragraph**, so
gold keeps that as one block. Parsers that segment on bold emphasis will split
it — recorded in `bold_spans` so the behaviour is measurable either way.

**p27 — prose plus ruled tables.** Two tables with identical geometry, each
with a two-level header where `Fund` is merged across both header rows
(`rowspan=2`) while `Std. Deviation` spans one column only. Only four column
groups are ruled; the sub-columns inside them are unruled and must be inferred.
Alternate-row grey banding is presentation and is deliberately not encoded.

**p30 — prose, lists and figures.** Two different bullet glyphs: a Symbol-font
private-use bullet (U+F0B7, set with **no** trailing space) for the body list
and U+2022 for the panel lists. Markers are stripped from item text and
preserved in `marker_raw`. Three of the embedded rasters are pure-white spacers
behind the panels and are deliberately *not* annotated as figures — only the
three icons and the logo are. Reading order through each panel is icon →
heading → list.

## Scoring tracks

Tracks exist so parsers of different classes are compared fairly — a text-only
extractor should not score zero on a page whose chart is a bitmap.

| track | scored over | notes |
|-------|-------------|-------|
| `text` | body blocks with `text` | character/word accuracy |
| `structure` | all blocks | block typing + reading order |
| `table` | `table` blocks | cell topology (TEDS / GriTS / cell F1) |
| `chart_data` | `chart` blocks | vision-only; `data_labels` scored as a set |
| `furniture` | headers/footers | opt-in; most parsers drop these legitimately |
| `cell_style` | coloured cells | opt-in; colour that carries meaning |

## Known limits

Stated so they are not mistaken for precision the gold does not have.

1. **Chart labels are not bound to individual bubbles.** Leader lines cross
   other marks and some marks are unlabelled, so a 1:1 binding would be
   guesswork. The 52 labels and the 53 measured marks are scored separately.
2. **13 of 53 bubbles are clipped** by the plot frame; their measured centres
   are biased inward. Score positions with tolerance, or filter on `clipped`.
3. **Bubble count is a measurement.** Heavily overlapping same-colour marks can
   merge into one blob. Treat `marks.n` as accurate to a couple of marks, and
   prefer the label set as the primary signal.
4. **`p04` header shape is genuinely ambiguous** — see `structure.ambiguities`.
   A scorer should accept either reading rather than penalise one.
5. Gold covers only what is *on the page*. It asserts nothing about semantics a
   parser might reasonably add (for example, inferring that `N/A` means null).
