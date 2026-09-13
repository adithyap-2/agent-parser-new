#!/usr/bin/env python
"""Negative tests for validate_gold.

A validator that passes everything proves nothing. Each case corrupts a copy of
a real gold file in one specific way and asserts the checker notices.
"""
import copy
import json
import sys

import validate_gold as V
from goldlib import GOLD


def check(name, page, mutate, expect):
    doc = json.loads((GOLD / f"{page}.json").read_text())
    mutate(doc)
    V.errors.clear(); V.warnings.clear()
    tmp = GOLD.parent / "_tmp_test.json"
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    try:
        V.check_page(tmp)
    finally:
        tmp.unlink()
    hit = [e for e in V.errors if expect in e]
    status = "ok  " if hit else "FAIL"
    print(f"  {status} {name}: {len(V.errors)} error(s)" +
          (f" -> {hit[0][:88]}" if hit else "  (expected a match for %r)" % expect))
    return bool(hit)


def drop_char(doc):
    for b in doc["blocks"]:
        if b.get("text"):
            b["text"] = b["text"][:-1]
            return


def invent_char(doc):
    for b in doc["blocks"]:
        if b.get("text"):
            b["text"] += "Z"
            return


def break_span(doc):
    for b in doc["blocks"]:
        if b["type"] == "table":
            b["structure"]["cells"][1]["colspan"] += 1   # now overlaps its neighbour
            return


def drop_cell(doc):
    for b in doc["blocks"]:
        if b["type"] == "table":
            b["structure"]["cells"] = [c for c in b["structure"]["cells"]
                                       if not (c["row"] == 5 and c["col"] == 3)]
            return


def scramble_order(doc):
    doc["reading_order"] = list(reversed(doc["reading_order"]))


def bad_bbox(doc):
    doc["blocks"][0]["bbox"] = [-5.0, 0.0, 10.0, 10.0]


def bad_list(doc):
    for b in doc["blocks"]:
        if b["type"] == "list":
            b["items"][0]["text"] = b["items"][0]["text"] + " tampered"
            return


CASES = [
    ("dropped character",      "p22", drop_char,      "missing from gold"),
    ("invented character",     "p22", invent_char,    "not on the page"),
    ("overlapping table span", "p27", break_span,     "covered twice"),
    ("missing table cell",     "p04", drop_cell,      "uncovered grid position"),
    ("scrambled reading order","p30", scramble_order, "reading_order[] does not match"),
    ("bbox off the page",      "p27", bad_bbox,       "outside the page"),
    ("list text != items",     "p30", bad_list,       "not its items joined"),
]

if __name__ == "__main__":
    print("validator negative tests")
    ok = all(check(*c) for c in CASES)
    V.errors.clear(); V.warnings.clear()
    print("\nall caught" if ok else "\nSOME CASES NOT CAUGHT")
    sys.exit(0 if ok else 1)
