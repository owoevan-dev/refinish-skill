#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python"]
# ///
"""Enlarge a part of a picture, with a grid numbered in the picture's own pixels, to read off where things are.

Usage:
  python scripts/zoom.py PICTURE.png x0,y0,x1,y1 OUT.jpg [--step 50] [--size 1000]

For writing hints (references/subject-file.md): the coordinates read on this grid are the picture's, whatever the
enlargement. Prints JSON: the output and the enlargement.
Exit codes: 0 done, 2 bad input.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import die, emit, load_rgba, over  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture")
    ap.add_argument("box", help="x0,y0,x1,y1 in the picture's pixels")
    ap.add_argument("out")
    ap.add_argument("--step", type=int, default=50, help="grid spacing in the picture's pixels")
    ap.add_argument("--size", type=int, default=1000, help="the enlarged picture's longer side")
    a = ap.parse_args()
    img, alpha = load_rgba(a.picture)
    h, w = alpha.shape
    try:
        x0, y0, x1, y1 = (int(v) for v in a.box.split(","))
    except ValueError:
        die("the box takes four integers: x0,y0,x1,y1")
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        die(f"the box is empty inside the {w}x{h} picture")
    z = a.size / float(max(x1 - x0, y1 - y0))
    crop = cv2.resize(over(img, alpha)[y0:y1, x0:x1], None, fx=z, fy=z, interpolation=cv2.INTER_CUBIC)
    for x in range((x0 // a.step + 1) * a.step, x1, a.step):
        px = int((x - x0) * z)
        cv2.line(crop, (px, 0), (px, crop.shape[0] - 1), (60, 60, 255), 1)
        cv2.putText(crop, str(x), (px + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1)
    for y in range((y0 // a.step + 1) * a.step, y1, a.step):
        py = int((y - y0) * z)
        cv2.line(crop, (0, py), (crop.shape[1] - 1, py), (60, 60, 255), 1)
        cv2.putText(crop, str(y), (2, py - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(a.out, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    emit({"out": a.out, "box": [x0, y0, x1, y1], "enlarged": round(z, 3)})


if __name__ == "__main__":
    main()
