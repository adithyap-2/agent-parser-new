"""Text normalisation levels for scoring.

Gold is stored verbatim (see gold/SCHEMA.md), so every comparison decision lives
here rather than being baked into the ground truth. A benchmark result is only
meaningful alongside the level it was computed at, so `score.py` always reports
the level it used.

  L0 raw          NFC + whitespace collapse. Nothing else. The strictest read:
                  smart quotes, superscripts and case all count.
  L1 typographic  + fold quotes/dashes/spaces to ASCII, expand ligatures, map
                  superscript digits down. This is the HEADLINE level: it stops
                  penalising a parser for emitting ' instead of ’, which is a
                  font-encoding artefact, not a reading error.
  L2 lenient      + casefold. Use when comparing parsers that normalise case in
                  headings; not the default, because case is real content.
"""
import re
import unicodedata

LEVELS = ("L0", "L1", "L2")

_FOLD = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "¹": "1", "²": "2", "³": "3",
    "⁰": "0", "⁴": "4", "⁵": "5", "⁶": "6",
    "⁷": "7", "⁸": "8", "⁹": "9",
    "•": "", "": "",          # list markers are presentation
    "…": "...",
}
_FOLD_RE = re.compile("|".join(map(re.escape, _FOLD)))


def normalize(s: str, level: str = "L1") -> str:
    if not s:
        return ""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}; expected one of {LEVELS}")
    s = unicodedata.normalize("NFC", s)
    if level in ("L1", "L2"):
        s = _FOLD_RE.sub(lambda m: _FOLD[m.group()], s)
    s = re.sub(r"\s+", " ", s).strip()
    if level == "L2":
        s = s.casefold()
    return s


def tokens(s: str, level: str = "L1") -> list:
    return normalize(s, level).split()


def norm_cell(s: str, level: str = "L1") -> str:
    """Cell text. Also strips thousands separators and unifies dash-as-empty.

    Financial tables render 'no value' as an em-dash run ('-----'), and a parser
    may reasonably emit '' or '-'. Treating those as equal keeps the table score
    about structure rather than about typographic filler.
    """
    s = normalize(s, level)
    if s and set(s) <= set("-–— "):
        return ""
    return s
