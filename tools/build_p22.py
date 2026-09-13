#!/usr/bin/env python
"""Gold builder — page 22: 'DISCLOSURES', dense single-column prose.

Structure notes (verified against benchmark/renders/p22_disclosures_text.png):

* Body line leading is ~8.0pt; paragraph separation is ~14pt. Paragraph breaks
  below are taken from that gap, not from sentence content.
* Seven bold run-in labels introduce topics. Six begin a paragraph; the
  seventh, "Characteristics:", starts *mid-line* at x=247.2 inside the
  "Holdings:" paragraph. Gold keeps that as ONE paragraph, faithful to the
  layout. Parsers that split on bold emphasis will segment differently — that
  is the point of including this page.
* The '18' at the foot is a page number -> region 'footer', furniture track.
"""
from goldlib import PageBuilder, literals

NOTES = (
    "Single-column justified 7pt prose, ~1560 words. Paragraph boundaries derive "
    "from the ~14pt inter-paragraph gap vs ~8pt line leading. The bold run-in label "
    "'Characteristics:' occurs mid-line inside the 'Holdings:' paragraph (b08) and "
    "does NOT open a new paragraph; b08 is deliberately one block. No hyphenation, "
    "no ligatures; superscript registered-sign glyphs are inline in the text layer."
)

b = PageBuilder(
    page_id="p22",
    page_pdf="p22_disclosures_text.pdf",
    render="p22_disclosures_text.png",
    page_number=22,
    profile=["prose", "dense-text"],
    notes=NOTES,
)

b.add("heading", lines=[0], level=1,
      bold_spans=literals("p22", "bold_spans", "heading"))

# Paragraph groupings by text-layer line index, from the y-gap analysis.
paras = list(zip(
    [list(range(1, 21)), list(range(21, 24)), list(range(24, 26)), [26],
     list(range(27, 30)), list(range(30, 32)), list(range(32, 40)),
     list(range(40, 45)), list(range(45, 49)), [49]],
    literals("p22", "bold_spans", "paras")))
for idxs, bold in paras:
    kw = {"bold_spans": bold} if bold else {}
    b.add("paragraph", lines=idxs, **kw)

b.add("footer", lines=[50], region="footer", tracks=("furniture", "structure"))

b.write()
