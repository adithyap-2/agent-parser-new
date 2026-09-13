#!/usr/bin/env python
"""Gold builder — page 13: bubble chart, almost entirely rasterised.

THE POINT OF THIS PAGE. The plot area (18,64)-(770,485) is a single 3132x1754
bitmap. Everything inside it — both axis titles, all tick labels, all ~52 data
labels and every leader line — exists ONLY as pixels. The text layer holds just
the page heading, the red banner, the KEY legend, three footnotes and the page
number. A text-extraction parser can therefore recover the page furniture and
score well on the `text` track while recovering nothing of the chart; only a
vision/OCR parser can touch the `chart_data` track. That separation is why the
page is in the benchmark.

How the chart gold was produced
-------------------------------
* Bubble positions, radii and colour classes are MEASURED, not eyeballed:
  detect_bubbles.py segments the bitmap per colour class and calibrates against
  the 0%/50%/100% gridlines it finds at px x=377/1534/2690 and y=220/946/1673.
* The colour palette is exact, taken from the KEY swatch grid, which is drawn as
  vector fills on the page rather than being part of the raster. Bubbles are
  painted at ~50% opacity over white.
* Data labels were transcribed by eye from six native-resolution tiles, then
  cross-checked against the ticker lists in the deck's own tables of contents
  (source pages 9-11), which independently confirm the spellings.

Labels are NOT bound 1:1 to bubbles. Many labels attach to their mark through a
leader line or arrow that crosses other marks, and several marks are unlabelled;
inventing a binding would put guesses into the gold. The label set and the mark
set are therefore scored separately. See chart.scoring_note.

READING ORDER. Below the chart the page splits into two groups: footnotes on the
left (x~20, y 514-540) and the KEY legend on the right (x~440-570, y 495-573).
They interleave vertically, so a strict top-to-bottom parser will emit them
mixed together. Gold orders them column-wise: footnotes, then legend.
"""
from goldlib import PageBuilder, join, union_bbox, literals
from detect_bubbles import PALETTE, measure

NOTES = (
    "The chart is a single raster: both axis titles, all tick labels, ~52 data labels "
    "and all leader lines are pixels only, so the text track and the chart_data track "
    "test different parser classes. Bubble geometry is measured from the bitmap and "
    "calibrated on the 0/50/100% gridlines; the palette is exact, read from the "
    "vector-drawn KEY swatches. Labels are deliberately NOT bound to individual "
    "bubbles because leader lines make many bindings ambiguous and some marks are "
    "unlabelled. READING ORDER: the bottom of the page is two side-by-side groups "
    "(left footnotes, right KEY legend) that interleave in y; gold orders them "
    "column-wise (footnotes then legend). A strict y-sort gives the interleaved "
    "order and should be treated as a reading-order failure, not a text failure."
)

# Transcribed from six native-resolution tiles of the raster; spellings verified
# against the ticker lists on source pages 9-11. Held outside version control
# because these are the document's content, not the benchmark's method.
DATA_LABELS = literals("p13", "data_labels")

LEGEND_ORDER = ["green", "green-yellow", "gold", "light-red", "red"]

b = PageBuilder(
    page_id="p13",
    page_pdf="p13_bubble_chart.pdf",
    render="p13_bubble_chart.png",
    page_number=13,
    profile=["chart", "rasterized-graphic", "two-column-footer"],
    notes=NOTES,
)
L = b.lines
assert len(L) == 16, f"expected 16 text lines, got {len(L)}"
assert L[2]["text"].strip() == "KEY", L[2]["text"]
assert L[15]["text"].strip() == "Page 10 of 22", L[15]["text"]

m = measure()
for bub in m["bubbles"]:
    r = bub["r_px"]
    bub["size_band"] = "large" if r >= 60 else "medium" if r >= 28 else "small"
    for k in ("cx", "cy", "area", "w", "h", "fill", "rgb"):
        bub.pop(k, None)
print(f"  measured {m['n']} bubbles; clipped={sum(x['clipped'] for x in m['bubbles'])}")

b.add("heading", lines=[0], level=1)
b.add("banner", lines=[1])

b.add("chart", text=None, bbox=[18.0, 64.0, 770.0, 485.0],
      tracks=("structure", "chart_data"),
      chart={
          "chart_type": "bubble",
          "rasterized": True,
          "raster": {"xref": 294, "px": [3132, 1754], "dpi_equiv": 300},
          "title": "Total Net Expense Percentile**",
          "axes": {
              "x": {"label": "Total Net Expense Percentile**",
                    "ticks": ["0%", "50%", "100%"], "direction": "left-to-right",
                    "note": "lower percentile = cheaper"},
              "y": {"label": "1 Year Performance Percentile*",
                    "ticks": ["0%", "50%", "100%"], "direction": "top-to-bottom",
                    "note": "axis is inverted; 0% is at the top"},
          },
          "encodings": {
              "x": "total net expense percentile vs peer group",
              "y": "1 year performance percentile vs peer group",
              "size": "fund AUM, relative",
              "color": "combined fee/performance quartile class",
          },
          "legend": {
              "block": "p13.b08",
              "classes": [{"class": c, "hex": "#%02x%02x%02x" % PALETTE[c]}
                          for c in LEGEND_ORDER],
              "note": "swatches are vector fills on the page, not part of the raster",
          },
          "calibration": {
              "plot_box_px": m["plot_box_px"],
              "gridlines_px": {"rows": m["grid_rows_px"], "cols": m["grid_cols_px"]},
              "method": "0/50/100% gridlines located in the bitmap",
          },
          "marks": {
              "n": m["n"],
              "method": "per-colour-class segmentation of the raster (tools/detect_bubbles.py)",
              "by_class": {c: sum(1 for x in m["bubbles"] if x["color_class"] == c)
                           for c in LEGEND_ORDER},
              "bubbles": m["bubbles"],
          },
          "data_labels": DATA_LABELS,
          "scoring_note": (
              "Score data_labels as a SET (recall/precision over 52 strings) — this is "
              "the primary chart_data signal. Score marks on count and colour-class "
              "distribution, and position only with tolerance: bubbles flagged clipped "
              "sit on the frame and their measured centre is biased inward. Do not "
              "expect a label-to-bubble binding; the page does not support one "
              "unambiguously."
          ),
      })

# Bottom-left footnote group, then bottom-right legend group. See module docstring.
b.add("caption", lines=[5], caption_for="p13.b03")
b.add("footnote", lines=[8])
b.add("footnote", lines=[10])
b.add("heading", lines=[2], level=3)

items, boxes = [], []
for idxs in ([3], [4, 6], [7, 9, 11], [12, 13], [14]):
    text, bbox = join(L, idxs)
    items.append({"text": text, "level": 0, "marker_raw": ""})
    boxes.append(bbox)
b.add("list", text="\n".join(i["text"] for i in items), bbox=union_bbox(boxes),
      marker_style="legend-swatch", items=items)

b.add("footer", lines=[15], region="footer", tracks=("furniture", "structure"))

b.write()
