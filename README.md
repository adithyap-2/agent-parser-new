# agent-parser-new

A small, rigorous benchmark for PDF parsers: a hand-built gold standard, a
calibrated scoring harness, and adapters for the parsers under test.

```
benchmark/   page selection + rationale
gold/        gold-standard schema, builders' output contract, README
tools/       gold builders, validator, negative tests
bench/       metrics, scorer, synthetic degradations, calibration, comparison
adapters/    parser -> benchmark IR (PyMuPDF, MinerU)
results/     findings write-up
```

## The data is not in this repo

The benchmark was built from a **private fund-board report**. Excluded from
version control:

| excluded | why |
|---|---|
| `*.pdf`, `*.png` | the source document and page renders |
| `gold/pages/*.json` | gold reproduces ~3,200 words of the source verbatim, plus every table value |
| `runs/**/*.json` | each parser's output — the same text again |
| `results/*.json` | per-block scoring detail, including text snippets |
| `tools/page_literals.json` | the few strings that can't be derived from geometry — chart labels transcribed from the bitmap, bold run-in spans, the publisher name |

That last one is why the builders look slightly indirect: hardcoding those
strings would have put document content in the source code, so they are read
from a data file instead. `tools/page_literals.example.json` shows the shape.

Everything that *describes* the method is here; everything that *contains* the
document is not. `results/README.md` keeps the scores and analysis, which carry
no document content.

## Running it on your own PDF

1. Drop a PDF in the project root and split the pages you want into
   `benchmark/pages/` (`pdfseparate`), rendering each to `benchmark/renders/`.
2. Write a builder per page in `tools/` (see `tools/build_p22.py` for the
   simplest). Character content comes from the PDF text layer via
   `tools/goldlib.py`; you supply the structure.
3. `python tools/build_all.py` — rebuilds all gold and validates it.
4. `python tools/test_validate_gold.py` — confirms the validator still catches
   corruption.
5. `python bench/synth.py && python bench/calibrate.py` — confirms the metrics
   still measure what they claim.
6. `python adapters/run_pymupdf.py && python bench/score.py runs/pymupdf`

## Design notes

Three ideas carry most of the weight:

- **Gold is generated, not edited.** Builders take characters from the PDF text
  layer and apply hand-authored structure, so gold cannot contain typos. Edit a
  builder, never the JSON.
- **Validate in both directions.** `validate_gold.py` compares character
  multisets gold-vs-page *and* page-vs-gold, catching both dropped and invented
  text. Its own blind spots are documented in `gold/README.md`.
- **Calibrate the metrics.** `bench/calibrate.py` runs 26 assertions against ten
  synthetic degradations. Each states a property the benchmark claims; if one
  fails, the metric is wrong, not the parser. This caught three real scoring
  bugs — see `results/README.md`.

Requires Python 3.11+, `pymupdf numpy scipy pillow rapidfuzz`. MinerU needs its
own environment (torch has no 3.14 wheels).
