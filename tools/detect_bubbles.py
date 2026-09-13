#!/usr/bin/env python
"""Detect the bubbles in the page-13 chart raster.

The chart is a bitmap, so bubble positions must be measured, not read. This
finds saturated (coloured) blobs, calibrates them against the plot frame, and
reports each bubble's centre in axis percentage units plus its radius and
colour class. Hand-transcribed labels are attached separately.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pymupdf
from scipy import ndimage

SCRATCH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")


def load():
    from goldlib import PAGES
    d = pymupdf.open(PAGES / "p13_bubble_chart.pdf")
    px = pymupdf.Pixmap(d, 294)
    if px.n > 4:
        px = pymupdf.Pixmap(pymupdf.csRGB, px)
    a = np.frombuffer(px.samples, dtype=np.uint8).reshape(px.height, px.width, px.n)
    return a[:, :, :3].astype(np.int16)


def calibrate(img):
    """Find the plot frame: the axis box drawn as solid dark lines."""
    g = img.mean(axis=2)
    dark = g < 160
    # Long horizontal / vertical runs = frame + gridlines.
    row_counts = dark.sum(axis=1)
    col_counts = dark.sum(axis=0)
    h_lines = np.where(row_counts > img.shape[1] * 0.55)[0]
    v_lines = np.where(col_counts > img.shape[0] * 0.55)[0]
    def group(idx):
        out, cur = [], [idx[0]]
        for i in idx[1:]:
            if i - cur[-1] <= 3:
                cur.append(i)
            else:
                out.append(int(np.mean(cur))); cur = [i]
        out.append(int(np.mean(cur)))
        return out
    return group(h_lines), group(v_lines)


def detect(img, y0, y1, x0, x1):
    """Segment per colour class.

    Detecting on one combined 'is coloured' mask fails two ways: closing the
    dashed-gridline gaps also welds in anti-aliasing fringe around the grey
    label text, and bubbles of different classes that overlap merge into one
    blob. Thresholding each class separately against its known blended colour
    avoids both.
    """
    frame = np.zeros(img.shape[:2], dtype=bool)
    frame[y0:y1, x0:x1] = True

    out = []
    for name, ref in CLASSES.items():
        d = np.sqrt(((img - np.array(ref)) ** 2).sum(axis=2))
        mask = (d < 42) & frame
        mask = ndimage.binary_closing(mask, structure=np.ones((9, 9)))
        mask = ndimage.binary_fill_holes(mask)
        lab, n = ndimage.label(mask)
        for i in range(1, n + 1):
            ys, xs = np.where(lab == i)
            area = len(ys)
            if area < 150:
                continue
            h, w = int(np.ptp(ys)) + 1, int(np.ptp(xs)) + 1
            if min(h, w) < 10:
                continue
            fill = area / (np.pi * (h / 2) * (w / 2))
            if fill < 0.62 or not (0.55 < w / h < 1.8):
                continue      # drop leader lines and legend rules
            cy, cx = ys.mean(), xs.mean()
            out.append({"cx": float(cx), "cy": float(cy), "r_px": float((h + w) / 4),
                        "area": int(area), "w": w, "h": h,
                        "fill": round(float(fill), 2), "color_class": name,
                        "rgb": [int(v) for v in img[ys, xs].mean(axis=0)]})
    return out


# Exact palette, read from the KEY swatch grid, which is drawn as vector fills
# on the page (not part of the raster). Bubbles are painted at ~50% opacity over
# white, so the on-page pixel colour is the swatch blended halfway to white.
PALETTE = {
    "green":        (0x00, 0x80, 0x00),
    "green-yellow": (0xAD, 0xFF, 0x2F),
    "gold":         (0xFF, 0xD7, 0x00),
    "light-red":    (0xFF, 0x63, 0x47),
    "red":          (0xFF, 0x00, 0x00),
}
CLASSES = {k: tuple((c + 255) / 2 for c in v) for k, v in PALETTE.items()}


def classify(rgb):
    best, bd = None, 1e9
    for name, ref in CLASSES.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, ref))
        if d < bd:
            bd, best = d, name
    return best


def measure():
    """Return the calibrated plot box and every detected bubble."""
    img = load()
    h_lines, v_lines = calibrate(img)
    top, bottom = h_lines[0], h_lines[-1]
    left, right = v_lines[0], v_lines[-1]
    bubbles = detect(img, top - 4, bottom + 4, left - 4, right + 4)
    for b in bubbles:
        b["x_pct"] = round((b["cx"] - left) / (right - left) * 100, 1)
        b["y_pct"] = round((b["cy"] - top) / (bottom - top) * 100, 1)
        # Marks touching the frame are cut off, so their centroid — and hence
        # the percentage derived from it — is pulled inward.
        b["clipped"] = bool(b["cx"] - b["r_px"] <= left + 2 or b["cx"] + b["r_px"] >= right - 2
                            or b["cy"] - b["r_px"] <= top + 2 or b["cy"] + b["r_px"] >= bottom - 2)
    bubbles.sort(key=lambda b: (b["y_pct"], b["x_pct"]))
    return {"plot_box_px": [left, top, right, bottom],
            "grid_rows_px": h_lines, "grid_cols_px": v_lines,
            "n": len(bubbles), "bubbles": bubbles}


if __name__ == "__main__":
    img = load()
    h_lines, v_lines = calibrate(img)
    print("horizontal frame/grid rows:", h_lines, file=sys.stderr)
    print("vertical  frame/grid cols:", v_lines, file=sys.stderr)

    top, bottom = h_lines[0], h_lines[-1]
    left, right = v_lines[0], v_lines[-1]
    print(f"plot box px: x {left}..{right}  y {top}..{bottom}", file=sys.stderr)

    bubbles = detect(img, top - 4, bottom + 4, left - 4, right + 4)
    for b in bubbles:
        b["x_pct"] = round((b["cx"] - left) / (right - left) * 100, 1)
        b["y_pct"] = round((b["cy"] - top) / (bottom - top) * 100, 1)

    bubbles.sort(key=lambda b: (-b["area"]))
    print(json.dumps({"plot_box_px": [left, top, right, bottom],
                      "n": len(bubbles), "bubbles": bubbles}, indent=1))
