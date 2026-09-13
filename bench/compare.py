#!/usr/bin/env python
"""Compare two or more parser runs side by side.

Usage:
    compare.py runs/pymupdf runs/mineru [--level L1] [--json results/compare.json]

Prints a per-track comparison, a per-page composite comparison, and a short
diagnostic section pulled from the sub-metrics — the sub-metrics are where the
interesting differences live, since a single composite hides whether a parser
lost characters or merely reordered them.
"""
import argparse
import json
import statistics
from pathlib import Path

import score as S

TRACKS = ["text", "structure", "table", "chart_data", "furniture"]
PAGES = ["p04", "p13", "p22", "p27", "p30"]


def load(run_dir, level):
    d = Path(run_dir)
    out = {}
    for p in sorted(d.glob("*.json")):
        gp = S.GOLD / p.name
        if gp.exists():
            out[p.stem] = S.score_page(gp, p, level)
    return {"name": d.name, "pages": out,
            "overall": statistics.fmean([r["composite"] for r in out.values()]) if out else 0.0}


def table(rows, headers):
    w = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    line = "| " + " | ".join(h.ljust(w[i]) for i, h in enumerate(headers)) + " |"
    sep = "|" + "|".join("-" * (x + 2) for x in w) + "|"
    body = ["| " + " | ".join(str(r[i]).ljust(w[i]) for i in range(len(r))) + " |" for r in rows]
    return "\n".join([line, sep] + body)


def fmt(v):
    return "—" if v is None else f"{v:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--level", default="L1")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    R = [load(r, a.level) for r in a.runs]
    names = [r["name"] for r in R]

    print(f"\nnormalisation: {a.level}\n")
    print("### Overall\n")
    rows = [[n, fmt(r["overall"])] for n, r in zip(names, R)]
    print(table(rows, ["parser", "composite"]))

    print("\n### By track (mean over applicable pages)\n")
    rows = []
    for n, r in zip(names, R):
        row = [n]
        for t in TRACKS:
            vals = [p["tracks"][t]["score"] for p in r["pages"].values() if t in p["tracks"]]
            row.append(fmt(statistics.fmean(vals) if vals else None))
        rows.append(row)
    print(table(rows, ["parser"] + TRACKS))

    print("\n### By page (composite)\n")
    rows = [[n] + [fmt(r["pages"][p]["composite"]) if p in r["pages"] else "—" for p in PAGES]
            for n, r in zip(names, R)]
    print(table(rows, ["parser"] + PAGES))

    for t in ("text", "structure", "table", "chart_data"):
        present = [p for p in PAGES if any(t in r["pages"].get(p, {}).get("tracks", {}) for r in R)]
        if not present:
            continue
        print(f"\n### {t} by page\n")
        rows = [[n] + [fmt(r["pages"][p]["tracks"][t]["score"])
                       if p in r["pages"] and t in r["pages"][p]["tracks"] else "—"
                       for p in present] for n, r in zip(names, R)]
        print(table(rows, ["parser"] + present))

    print("\n### Diagnostics\n")
    for n, r in zip(names, R):
        print(f"**{n}**")
        for p in PAGES:
            if p not in r["pages"]:
                continue
            tr = r["pages"][p]["tracks"]
            bits = []
            if "text" in tr:
                bits.append(f"cer={tr['text']['cer']:.3f} aligned={tr['text']['cer_aligned']:.3f}"
                            f" orderpen={tr['text']['order_penalty']:.3f}")
            if "structure" in tr:
                st = tr["structure"]
                bits.append(f"blockF1={st['block_detection_f1']:.2f}"
                            f" type={st['type_accuracy_coarse']:.2f}"
                            f" tau={st['reading_order_tau']:.2f}"
                            f" missed={len(st['missed_blocks'])} spurious={st['spurious_blocks']}")
            if "table" in tr and tr["table"].get("tables"):
                for i, t0 in enumerate(tr["table"]["tables"]):
                    bits.append(f"tbl{i} con={t0['grits_con']:.2f} top={t0['grits_top']:.2f}"
                                f" hdr={t0['header_f1']:.2f} bag={t0['cell_bag_f1']:.2f}"
                                f" shape{t0['pred_shape']}vs{t0['gold_shape']}")
            elif "table" in tr:
                bits.append(f"table n_pred={tr['table'].get('n_pred')} ({tr['table'].get('note','')})")
            if "chart_data" in tr:
                cd = tr["chart_data"]
                bits.append(f"chart labelF1={cd['labels']['f1']:.2f} "
                            f"recall={cd['labels']['recall']:.2f}")
            print(f"  {p}: " + "; ".join(bits))
        print()

    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(
            {"level": a.level, "runs": R}, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
