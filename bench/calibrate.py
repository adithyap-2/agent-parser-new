#!/usr/bin/env python
"""Calibrate the metric suite against the synthetic degradations.

Each assertion states the behaviour the benchmark claims to have. If one fails,
the metric is wrong — not the parser. Run this after any change to metrics.py
or score.py.
"""
import statistics
import sys
from pathlib import Path

import score as S

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
TRACKS = ["text", "structure", "table", "chart_data", "furniture"]


def run(name, level="L1"):
    d = RUNS / f"_synth_{name}"
    pages = [S.score_page(S.GOLD / p.name, p, level) for p in sorted(d.glob("*.json"))]
    by_track = {}
    for t in TRACKS:
        vals = [p["tracks"][t]["score"] for p in pages if t in p["tracks"]]
        by_track[t] = statistics.fmean(vals) if vals else None
    return {"pages": {p["page_id"]: p for p in pages},
            "overall": statistics.fmean([p["composite"] for p in pages]),
            "tracks": by_track}


NAMES = ["perfect", "text_only", "dropped_na_cells", "flat_header", "y_sorted",
         "noisy_text", "merged_paragraphs", "no_chart_labels", "half_chart_labels", "alt_header"]

R = {n: run(n) for n in NAMES}

hdr = f"{'degradation':20s} {'overall':>7s} " + " ".join(f"{t:>10s}" for t in TRACKS)
print(hdr); print("-" * len(hdr))
for n in NAMES:
    r = R[n]
    row = f"{n:20s} {r['overall']:7.3f} "
    for t in TRACKS:
        v = r["tracks"][t]
        row += f"{v:10.3f} " if v is not None else f"{'-':>10s} "
    print(row)

print("\nper-page composite")
hdr2 = f"{'degradation':20s} " + " ".join(f"{p:>7s}" for p in ["p04", "p13", "p22", "p27", "p30"])
print(hdr2); print("-" * len(hdr2))
for n in NAMES:
    row = f"{n:20s} "
    for p in ["p04", "p13", "p22", "p27", "p30"]:
        row += f"{R[n]['pages'][p]['composite']:7.3f} "
    print(row)

# --------------------------------------------------------------------------
CHECKS = []


def check(desc, cond):
    CHECKS.append((desc, bool(cond)))


P = R["perfect"]
check("perfect scores 1.000 on every track",
      all(v is None or abs(v - 1.0) < 1e-9 for v in P["tracks"].values()))
check("perfect scores 1.000 overall", abs(P["overall"] - 1.0) < 1e-9)

check("text_only destroys the table track", R["text_only"]["tracks"]["table"] < 0.35)
check("text_only destroys the chart track", R["text_only"]["tracks"]["chart_data"] < 0.05)
check("text_only keeps most text",         R["text_only"]["tracks"]["text"] > 0.90)

# Column shift is a CONTENT failure, not a topology one: the parser keeps a
# well-formed 29x14 grid with correct headers and merely puts values in the
# wrong cells. grits_con must fall hard while grits_top and header_f1 hold.
_na = R["dropped_na_cells"]["pages"]["p04"]["tracks"]["table"]["tables"][0]
check("dropping no-value cells shifts columns (content)", _na["grits_con"] < 0.80)
check("...while leaving topology untouched",              _na["grits_top"] > 0.99)
check("...and leaving the header intact",                 _na["header_f1"] > 0.99)
check("cell_bag_f1 shows the values themselves survive",  _na["cell_bag_f1"] > 0.80)
check("dropping no-value cells leaves prose text intact",
      R["dropped_na_cells"]["pages"]["p22"]["tracks"]["text"]["score"] > 0.99)

check("flattening spans hurts table topology",
      R["flat_header"]["pages"]["p27"]["tracks"]["table"]["tables"][0]["grits_top"] < 1.0)
check("flattening spans leaves cell content intact",
      R["flat_header"]["pages"]["p27"]["tracks"]["table"]["tables"][0]["cell_bag_f1"] > 0.99)

check("y-sorting breaks p13 reading order",
      R["y_sorted"]["pages"]["p13"]["tracks"]["structure"]["reading_order_tau"] < 1.0)
check("y-sorting DOES cost p13 the headline text score (order is content)",
      R["y_sorted"]["pages"]["p13"]["tracks"]["text"]["cer"] > 0.02)
check("...but cer_aligned isolates it as pure ordering, not lost characters",
      R["y_sorted"]["pages"]["p13"]["tracks"]["text"]["cer_aligned"] < 1e-9)
check("order_penalty attributes the whole gap to ordering",
      R["y_sorted"]["pages"]["p13"]["tracks"]["text"]["order_penalty"] > 0.02)
check("y-sorting leaves single-column pages alone",
      abs(R["y_sorted"]["pages"]["p22"]["composite"] - 1.0) < 1e-9)

check("2% char noise shows up in text", R["noisy_text"]["tracks"]["text"] < 0.99)
check("2% char noise is not catastrophic", R["noisy_text"]["tracks"]["text"] > 0.90)

check("merging paragraphs hurts structure",
      R["merged_paragraphs"]["pages"]["p22"]["tracks"]["structure"]["score"] < 0.9)
check("merging paragraphs preserves text",
      R["merged_paragraphs"]["pages"]["p22"]["tracks"]["text"]["score"] > 0.99)

check("no chart labels tanks chart_data",
      R["no_chart_labels"]["tracks"]["chart_data"] < 0.25)
check("half the chart labels lands mid-range",
      0.25 < R["half_chart_labels"]["tracks"]["chart_data"] < 0.85)
check("chart label recall tracks the degradation",
      abs(R["half_chart_labels"]["pages"]["p13"]["tracks"]["chart_data"]["labels"]["recall"]
          - 0.5) < 0.05)

_alt = R["alt_header"]["pages"]["p04"]["tracks"]["table"]["tables"][0]
check("the accepted alternative header reading scores ~1.0",
      _alt["combined"] > 0.99)
check("...and the scorer reports which variant it used",
      _alt["variant_used"] == "rowspan2_alternative")

print("\ncalibration checks")
ok = True
for desc, passed in CHECKS:
    print(f"  {'ok  ' if passed else 'FAIL'} {desc}")
    ok &= passed
print("\nall checks passed" if ok else "\nCALIBRATION FAILURES")
sys.exit(0 if ok else 1)
