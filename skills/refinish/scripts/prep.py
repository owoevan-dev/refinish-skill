#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python"]
# ///
"""Make a source picture ready to re-finish: crop it to the figure and enlarge it the traditional way.

Usage:
  python scripts/prep.py SRC.png OUT.png [--scale 2] [--box x0,y0,x1,y1] [--margin 10] [--grid]

Enlarging is Lanczos on colour premultiplied by alpha (a cut-out's edge keeps no fringe); no neural upscaler, so
nothing is invented. The engines redraw the lines and the paint at the new size, which is what makes the result
crisp; record the factor as "upscaled" in the subject file. --grid also writes OUT_grid.jpg with a coordinate grid
every 100 px, to place a subject file's samples and outlines by. Prints JSON: the crop box and the new size.
Exit codes: 0 done, 2 bad input.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import die, emit, load_rgba, over, resize_premultiplied, save_rgba, write_image  # noqa: E402


def grid(bgr, step=100):
    img = bgr.copy()
    h, w = img.shape[:2]
    for x in range(0, w, step):
        cv2.line(img, (x, 0), (x, h - 1), (60, 160, 255) if x % 500 else (40, 40, 230), 1)
        cv2.putText(img, str(x), (x + 3, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 40, 230), 2)
    for y in range(0, h, step):
        cv2.line(img, (0, y), (w - 1, y), (60, 160, 255) if y % 500 else (40, 40, 230), 1)
        cv2.putText(img, str(y), (3, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 40, 230), 2)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--scale", type=int, default=2, help="enlargement factor (1 to crop only)")
    ap.add_argument("--box", help="x0,y0,x1,y1 in the source; default: the figure's bounds plus the margin")
    ap.add_argument("--margin", type=int, default=10)
    ap.add_argument("--grid", action="store_true")
    a = ap.parse_args()
    if a.scale < 1 or a.scale > 4:
        die("--scale must be 1 to 4")
    img, alpha = load_rgba(a.src)
    h, w = alpha.shape
    if a.box:
        try:
            x0, y0, x1, y1 = (int(v) for v in a.box.split(","))
        except ValueError:
            die("--box takes four integers: x0,y0,x1,y1")
    else:
        ys, xs = np.nonzero(alpha > 0.03)
        if not len(ys):
            die(f"{a.src} is fully transparent")
        m = a.margin
        x0, y0 = max(0, xs.min() - m), max(0, ys.min() - m)
        x1, y1 = min(w, xs.max() + 1 + m), min(h, ys.max() + 1 + m)
    img, alpha = img[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    if a.scale > 1:
        img, alpha = resize_premultiplied(img, alpha, ((x1 - x0) * a.scale, (y1 - y0) * a.scale), cv2.INTER_LANCZOS4)
    save_rgba(a.out, img, alpha)
    res = {"out": a.out, "box": [int(x0), int(y0), int(x1), int(y1)], "size": [int(alpha.shape[1]), int(alpha.shape[0])],
           "upscaled": a.scale}
    if a.grid:
        gp = str(Path(a.out).with_name(Path(a.out).stem + "_grid.jpg"))
        write_image(gp, grid(over(img, alpha)), [cv2.IMWRITE_JPEG_QUALITY, 90])
        res["grid"] = gp
    emit(res)


if __name__ == "__main__":
    main()
