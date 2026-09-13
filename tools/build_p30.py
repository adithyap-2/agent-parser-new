#!/usr/bin/env python
"""Gold builder — page 30: 'Report Details and Methodology', prose + lists + figures.

Two list marker styles appear and both are stripped from item text:

  * body list  -> U+F0B7, a Symbol-font private-use bullet, set with NO space
                  before the item text ('\\uf0b7The number of funds...')
  * panel list -> U+2022 '•' followed by a space

Images: xrefs 631 and 634 are pure-white spacer rasters behind the three
panels (verified: a single sampled colour) and are NOT emitted as blocks.
Only the three blue line-art icons and the footer logo are real figures.

Reading order through the panel section is icon -> heading -> list, repeated
three times. The icons sit in a left gutter (x 85-143) beside their text
(x 168-573); a parser using strict top-to-bottom ordering will agree, but one
that segments columns may emit all three icons before any panel text.
"""
from goldlib import PageBuilder, join, union_bbox, literals

NOTES = (
    "Portrait page: narrative prose, a bulleted list using a Symbol-font private-use "
    "bullet (U+F0B7, no trailing space), then three icon+heading+bullets panels using "
    "U+2022 bullets. List markers are excluded from item text and recorded in "
    "marker_raw. The wide rasters behind the panels (xref 631 used twice, xref 634) "
    "are pure-white spacers, deliberately not annotated as figures. Panel reading "
    "order is icon, heading, then list."
)

b = PageBuilder(
    page_id="p30",
    page_pdf="p30_methodology_figures.pdf",
    render="p30_methodology_figures.png",
    page_number=30,
    profile=["prose", "list", "figure", "mixed"],
    notes=NOTES,
)
L = b.lines

assert len(L) == 38, f"expected 38 text lines, got {len(L)}"
assert L[0]["text"].startswith("Report Details"), L[0]["text"]
assert L[11]["text"].startswith("The number"), repr(L[11]["text"])
assert L[19]["text"].startswith("INVESTMENT"), L[19]["text"]
assert L[35]["text"].startswith("• Unique"), repr(L[35]["text"])


def add_list(items, marker_raw, marker_style="bullet", level=0):
    built, boxes = [], []
    for idxs in items:
        text, bbox = join(L, idxs)
        for m in ("\uf0b7", "\u2022 ", "\u2022"):
            if text.startswith(m):
                text = text[len(m):].lstrip()
                break
        built.append({"text": text, "level": level, "marker_raw": marker_raw})
        boxes.append(bbox)
    b.add("list", text="\n".join(i["text"] for i in built), bbox=union_bbox(boxes),
          marker_style=marker_style, items=built)


b.add("title", lines=[0])
b.add("paragraph", lines=[1, 2, 3, 4])
b.add("paragraph", lines=[5, 6, 7, 8, 9, 10])
add_list([[11], [12, 13], [14], [15]], marker_raw="\uf0b7")
b.add("paragraph", lines=[16, 17, 18])

PANELS = [
    # (icon xref, icon px, icon bbox, description, heading line, item line-groups)
    (638, [107, 91], [90.0, 427.0, 141.0, 471.0],
     "Magnifying glass, white line art on a dark blue square",
     19, [[20, 21, 22, 23, 24]]),
    (641, [122, 65], [85.0, 531.0, 143.0, 562.0],
     "Ruler, white line art on a dark blue square",
     25, [[26, 27, 28, 29]]),
    (635, [98, 98], [92.0, 618.0, 139.0, 665.0],
     "Globe / wire-frame sphere, white line art on a dark blue square",
     30, [[31, 32], [33, 34], [35]]),
]
for xref, px, bbox, desc, head, items in PANELS:
    b.add("figure", text=None, bbox=bbox, tracks=("structure",),
          figure={"kind": "icon", "raster": {"xref": xref, "px": px},
                  "description": desc, "contains_text": False})
    b.add("heading", lines=[head], level=3)
    add_list(items, marker_raw="\u2022")

b.add("footer", lines=[36], region="footer", tracks=("furniture", "structure"))
b.add("figure", text=None, bbox=[468.0, 734.0, 539.0, 777.0], region="footer",
      tracks=("furniture", "structure"),
      figure={"kind": "logo", "raster": {"xref": 630, "px": [150, 91]},
              "description": literals("logo", "description"), "contains_text": True,
              "text_in_image": literals("logo", "text_in_image")})
b.add("footer", lines=[37], region="footer", tracks=("furniture", "structure"))

b.write()
