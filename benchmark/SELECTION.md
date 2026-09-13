# Benchmark Page Selection

Source: `parser-benchmark.pdf` (30 pages, letter, mixed orientation).
The source is a stitched compilation of fund-board reports — page footers show
differing internal pagination ("Page 6 of 22", "Page 7 of 153"), so pages are
independent and can be parsed standalone.

## Selected pages

| # | Source pg | File | Orientation | Primary content | What it stresses |
|---|-----------|------|-------------|-----------------|------------------|
| 1 | 4 | `p04_exec_summary_table.pdf` | Landscape | Wide financial table | Multi-level spanning headers, 13 numeric cols, colour-encoded cells, `N/A` sentinels, footnote superscripts |
| 2 | 13 | `p13_bubble_chart.pdf` | Landscape | Bubble/scatter chart | Vector graphics, ~45 overlapping labelled bubbles, leader lines, 2 encoded dimensions + size, multi-line colour legend |
| 3 | 22 | `p22_disclosures_text.pdf` | Landscape | Dense prose | Full-width justified 6pt text, ~1,560 words, no structure cues, paragraph segmentation + reading order |
| 4 | 27 | `p27_notes_plus_tables.pdf` | Portrait | Text **+** two tables | Heading hierarchy, narrative, then bordered tables with grouped headers (Total Return / Sharpe / Std Dev × 1/3/5 Yr), negative numbers |
| 5 | 30 | `p30_methodology_figures.pdf` | Portrait | Text + bullets + figures | 3 embedded raster icons with captions, nested bullet lists, prose interleaved with figure blocks |

Combined: `benchmark-5page.pdf`. Renders at 200 dpi in `renders/`.

## Coverage rationale

- **Tables**: two distinct regimes — a wide landscape grid with hierarchical
  headers (pg 4) and portrait bordered tables embedded in prose (pg 27).
- **Charts/graphs**: pg 13 is the only true data-graphic type in the document;
  it is the densest of the four bubble-chart pages (pgs 12–15).
- **Text**: pg 22 is the worst-case prose page (smallest type, highest word
  count, zero layout scaffolding).
- **Mixed / figures**: pg 30 is the only page combining narrative, bullets and
  raster imagery.
- **Orientation**: 3 landscape / 2 portrait.
- **Graphics type**: vector (pg 13) and raster (pg 30) both represented.

## Rejected candidates worth noting

- pgs 9–11 (Tables of Contents, dot leaders) — a classic parser failure mode but
  narrow; held in reserve if the benchmark is widened.
- pgs 6–8 (4pt borderless expense grids) — extreme small-type tables, redundant
  with pg 4 for header-structure testing.
- pgs 16–17 (agenda with deep outline numbering) — good hierarchy test, no
  tabular or graphic content.
- pgs 14–15 — same chart template as 13 but only 1–2 data points; too sparse to
  discriminate between parsers.
- pgs 28–29 (title/divider pages) — near-empty, no signal.
