# Results — PyMuPDF vs MinerU vs Docling

Normalisation **L1**. Reproduce with:

```bash
.venv/bin/python adapters/run_pymupdf.py

# MinerU and Docling each need their own env (torch has no Python 3.14 wheels):
MINERU_MODEL_SOURCE=modelscope /opt/anaconda3/envs/mineru/bin/mineru \
    -p benchmark/benchmark-5page.pdf -o /tmp/mineru_out -b pipeline -m txt
.venv/bin/python adapters/run_mineru.py

/opt/anaconda3/envs/docling/bin/python adapters/run_docling.py

.venv/bin/python bench/compare.py runs/pymupdf runs/mineru runs/docling
```

| parser | version | how |
|---|---|---|
| PyMuPDF | 1.28.2 | text layer + `find_tables()`; baseline |
| MinerU | 3.4.5 | `pipeline` backend, `-m txt`, CPU |
| Docling | 2.127.0 | default pipeline, CPU, RapidOCR enabled (~2 min for 5 pages) |

## Overall

| parser | composite |
|---|---|
| PyMuPDF | 0.738 |
| MinerU | 0.741 |
| **Docling** | **0.909** |

Docling wins, and unlike the PyMuPDF/MinerU near-tie this margin is real: it
leads on **every** track, not on an average that hides a trade-off.

## By track

| parser | text | structure | table | chart_data | furniture |
|---|---|---|---|---|---|
| PyMuPDF | 0.888 | 0.881 | 0.537 | 0.000 | 0.800 |
| MinerU | 0.849 | 0.821 | 0.711 | 0.000 | 1.000 |
| **Docling** | **0.984** | **0.933** | **0.944** | **0.479** | **1.000** |

## By page (composite)

| parser | p04 table | p13 chart | p22 prose | p27 mixed | p30 lists |
|---|---|---|---|---|---|
| PyMuPDF | 0.820 | 0.337 | 1.000 | 0.601 | 0.934 |
| MinerU | 0.641 | 0.243 | 0.996 | 0.923 | 0.903 |
| Docling | 0.947 | 0.647 | 0.999 | 0.974 | 0.979 |

### table track, per page

| parser | p04 (14 cols, ragged header) | p27 (unruled sub-columns) |
|---|---|---|
| PyMuPDF | 0.743 | 0.332 |
| MinerU | 0.525 | 0.896 |
| Docling | **0.919** | **0.969** |

## What happened

**Docling is the first parser to read the chart.** `chart_data` 0.479 against
0.000 for both others — it recovered **44 of 52** bubble labels by OCR
(precision 0.90, recall 0.85, F1 0.87). All 8 "misses" are really OCR merges of
adjacent labels — two tickers run together as one token, three fused without a
separator, and a long fund name absorbed into the ticker beside it. The
characters were read; the token boundaries were not.

The score is 0.479 rather than 0.87 because labels are only 55% of the track.
Docling scores **0** on mark count, colour distribution and axis labels — it
read the *text* in the bitmap but did no chart *understanding*: no bubbles
counted, no axis semantics. It even OCR'd the axis title
("Total Net Expense Percentile\*\*") but emitted it as a page heading, with no
notion that it labels an axis. That is the honest split, and it is exactly the
distinction the track was built to expose.

**Docling resolves both table traps that split the other two.** PyMuPDF and
MinerU each won one page and lost the other; Docling gets both:

- *p04* — grid exactly right (`[29,14]`), `grits_con` **1.00**. MinerU
  over-segmented this into 25 columns; PyMuPDF got the columns but emitted no
  spans at all.
- *p27* — both tables exact (`[15,8]`, `[14,8]`), `grits_con` 0.99. PyMuPDF
  collapsed the unruled sub-columns here into `[12,4]`.

Its remaining table gap is header spans: `header_f1` 0.68 on p04, 0.91 on p27 —
it gets the grid right but not every merged header cell.

**Where Docling still loses points:** p13 structure, 0.738. It splits the KEY
legend into **12 blocks**, breaking each entry at the bold colour name
("Green" / ": Fund is better than median…"). Gold has one list of 5 items.
That is genuine over-segmentation on bold run-in labels — the same behaviour
the p22 `Characteristics:` trap targets — and it is why p13's `block_detection_f1`
is 0.41 with 15 spurious blocks despite near-perfect text.

**Text is close to solved for all three on prose.** p22 is ~1.000 for everyone.
The parsers separate on structure and tables, not on reading running text.

## Five scoring/adapter bugs this project exposed

Each inflated or deflated scores for reasons unrelated to parser quality.
Calibration stayed at 26/26 after every fix.

1. **Table text uncredited** — gold puts table content on the text track; a
   parser emitting `structure` with no `text` scored 0 for it. PyMuPDF p04:
   0.005 → 1.000.
2. **`is_header` punished a format** — MinerU emits `<td>` with no `<th>`, so
   header comparisons scored 0 despite correct spans. Now inferred
   positionally. MinerU p27 table: 0.711 → 0.896.
3. **MinerU adapter invented a reading-order error** — appending
   `discarded_blocks` at the end put p04's heading after the table, forcing
   τ to 0.00. Placing them by bbox gives MinerU τ = 1.00 on all five pages.
   Overall 0.702 → 0.741, which *flipped the ranking* against PyMuPDF.
4. **Docling adapter dropped all furniture** — `iterate_items()` walks only
   `doc.body`, and Docling holds `page_header`/`page_footer` outside it. It had
   detected 3 headers and 9 footers; the adapter saw none. Furniture 0.000 →
   1.000.
5. **Docling adapter threw away the chart** — `iterate_items()` does not
   descend into pictures, so the OCR text nested in the chart element was
   invisible. This was worth the whole chart track: overall 0.863 → 0.909,
   p13 0.415 → 0.647.

Bugs 3–5 are the same lesson in three costumes: **the adapter decides what the
parser appears to be capable of.** Two of them made a parser look strictly worse
than it is, and one changed which parser came first. Sub-metrics are what made
them findable.

## Caveats

- **n=5.** Docling's 0.17 lead over the other two is well outside noise at this
  size, but the PyMuPDF/MinerU gap of 0.003 is meaningless. These results
  characterise failure modes; only the large gaps rank tools.
- **MinerU ran CPU-only on `pipeline`.** Its `vlm-engine` / `hybrid-engine`
  backends are the accurate ones and would likely change both the chart and
  wide-table results. This is MinerU's floor, not its ceiling.
- **Docling's chart score depends on an adapter decision.** The OCR strings are
  Docling's, but grouping them into `data_labels` is the adapter's doing;
  pure numeric/percent tokens were filtered as axis ticks by a generic rule
  (not derived from gold). A naive Docling integration that only walks
  `iterate_items()` would score 0.000 here.
- **Weights are a judgement** (`PAGE_WEIGHTS` in `bench/score.py`); p04 is 65%
  table, so table handling dominates that page.
- **No positional scoring** — blocks are matched by text, so bbox accuracy is
  not assessed.
