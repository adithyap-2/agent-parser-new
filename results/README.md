# Results — PyMuPDF vs MinerU

Normalisation **L1**. Reproduce with:

```bash
.venv/bin/python adapters/run_pymupdf.py
# MinerU runs in its own env (torch has no Python 3.14 wheels):
MINERU_MODEL_SOURCE=modelscope /opt/anaconda3/envs/mineru/bin/mineru \
    -p benchmark/benchmark-5page.pdf -o /tmp/mineru_out -b pipeline -m txt
.venv/bin/python adapters/run_mineru.py
.venv/bin/python bench/compare.py runs/pymupdf runs/mineru
```

| parser | version | how |
|---|---|---|
| PyMuPDF | 1.28.2 | text layer + `find_tables()`; baseline |
| MinerU | 3.4.5 | `pipeline` backend, `-m txt`, CPU (ModelScope weights) |

## Overall

| parser | composite |
|---|---|
| PyMuPDF | 0.738 |
| **MinerU** | **0.741** |

The single number is a near-tie and is the least useful thing here — the two
parsers fail in completely different places. Read the tracks.

## By track

| parser | text | structure | table | chart_data | furniture |
|---|---|---|---|---|---|
| PyMuPDF | **0.888** | **0.881** | 0.537 | 0.000 | 0.800 |
| MinerU | 0.849 | 0.821 | **0.711** | 0.000 | **1.000** |

## By page (composite)

| parser | p04 table | p13 chart | p22 prose | p27 mixed | p30 lists |
|---|---|---|---|---|---|
| PyMuPDF | **0.820** | **0.337** | **1.000** | 0.601 | **0.934** |
| MinerU | 0.641 | 0.243 | 0.996 | **0.923** | 0.903 |

### table track, per page

| parser | p04 | p27 |
|---|---|---|
| PyMuPDF | **0.743** | 0.332 |
| MinerU | 0.525 | **0.896** |

## What actually happened

**Neither parser reads the chart.** Both score 0.000 on `chart_data`. p13's plot
is a single bitmap, and neither tool attempts chart-data extraction — MinerU's
pipeline backend detects the region and crops it to an image, nothing more. This
is the benchmark's designed discriminator and it currently separates nobody;
it will only move with a VLM backend.

**PyMuPDF wins the unruled table, MinerU wins the ruled one.** The reversal on
the table track is the most interesting result:

- *p27*: PyMuPDF detects only the 4 **ruled** column groups and collapses each
  group's three unruled sub-columns into one cell — `'2.42 0.10 4.26'` instead
  of three values. Shape `[12,4]` against gold's `[15,8]`, `cell_bag_f1` 0.26.
  MinerU's table model recovers the grid **exactly** — `[15,8]`, `grits_con`
  0.99 — including `rowspan=2` on *Fund* and `colspan=3` on *Total Return*.
- *p04*: the reverse. PyMuPDF's ruled-grid detector gets the 14 columns right
  (`grits_con` 0.95) but emits no spans at all (`header_f1` 0.17). MinerU
  over-segments the wide table into **25 columns** against gold's 14
  (`grits_con` 0.68) — though `cell_bag_f1` 0.97 shows it *read* nearly every
  value, then placed them in the wrong grid.

So: PyMuPDF is bounded by needing ruled lines; MinerU's learned model handles
unruled structure well but destabilises on a very wide table.

**PyMuPDF's p13 score is pure reading order.** `cer` 0.465 with `cer_aligned`
0.000 — every character correct, the two-column footer interleaved. MinerU's
p13 is the opposite failure: `cer` 0.701 with `order_penalty` 0.000, because it
**discarded** three footnotes and the *KEY* heading as page furniture. Same
track, same rough score, opposite causes — visible only because the text track
decomposes.

**MinerU discards more.** It classified p04's red banner and several body
elements as furniture. That gives it a perfect 1.000 on the opt-in `furniture`
track and costs it on `structure` (p04 type accuracy 0.50). PyMuPDF keeps
everything and instead emits spurious blocks (9 on p13, 7 on p27).

**p22 is solved.** Both parsers are ~1.000 on 1,560 words of dense prose. Plain
text extraction is not where these tools differ.

## Three scoring bugs this run exposed

All three inflated or deflated scores for reasons that had nothing to do with
parser quality. Fixed, with calibration still at 26/26.

1. **Table text wasn't credited.** Gold puts table content on the text track; a
   parser emitting a table as `structure` with no `text` field got zero for it.
   PyMuPDF's p04 text score was 0.005 before the fix, 1.000 after.
2. **`is_header` punished a format, not a parser.** MinerU emits table HTML with
   `<td>` throughout and no `<th>`/`<thead>`, so every header comparison scored
   0 despite the spans being right. `infer_headers()` now marks the top N rows
   positionally when a parser flags none. MinerU's p27 table: 0.711 → **0.896**.
3. **My own adapter invented a reading-order error.** Appending MinerU's
   `discarded_blocks` at the end of the block list put p04's page heading after
   the table, driving reading-order τ to 0.00. Placing them by bbox instead
   gives MinerU **τ = 1.00 on all five pages** — its reading order was perfect
   the whole time. MinerU overall: 0.702 → **0.741**.

The third is worth dwelling on: it changed the headline ranking. Before the fix
PyMuPDF appeared to win 0.738 to 0.702; after it, the two are level. An adapter
bug is indistinguishable from a parser weakness unless you look at the
sub-metrics, which is the argument for keeping them.

## Caveats

- **n=5.** A 0.003 gap in the composite is noise. These results characterise
  failure modes; they do not rank the tools.
- **MinerU ran on CPU with the `pipeline` backend.** Its `vlm-engine` /
  `hybrid-engine` backends are the accurate ones and would likely change the
  chart and wide-table results. This is a floor for MinerU, not its ceiling.
- **Weights are a judgement** (`PAGE_WEIGHTS` in `bench/score.py`). p04's
  composite is 65% table, so MinerU's column over-segmentation dominates that
  page's number.
- **No positional scoring** — blocks are matched by text, so neither parser is
  assessed on bbox accuracy.
