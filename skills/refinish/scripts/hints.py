#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Help with a hints file for scripts/auto_parts.py: where its points land, and points for the regions a review
picture numbers.

Usage:
  python scripts/hints.py check HINTS.json SUBJECT.json
  python scripts/hints.py points SUBJECT.json 12 40 77
  python scripts/hints.py pick IMAGE x0,y0,x1,y1 [--like x,y | --near L,a,b] [--tol 12] [-n 1]

check: for each point, the region under it, the part the subject gives that region now and the picture's colour
there (CIE Lab); a point outside the figure, or on a colour far from the other points of its part, is marked. Run it
before auto_parts.py --hints: a point read off a grid is often a few dozen pixels off, on the background or on the
thing next to it.
points: the point deepest inside each region numbered (the numbers on <subject>.auto.jpg), with its colour, to copy
into a hints file; reading a region's number off the review is surer than reading coordinates.
pick: points deep inside one colour within a box, on the figure: the colour under a point you read off a grid
(--like), a colour given (--near, Lab), or, with neither, each of the box's main colours. A point read off a grid
lands on the background or the thing beside the part more often than anywhere else; a picked point lies in the middle
of its colour's largest patch, as far from its edges as the patch allows.
Prints JSON. Exit codes: 0 done (check: no point marked), 1 check marked some points, 2 bad input.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import die, emit, lab, load_rgba  # noqa: E402
from _style import load_subject, subject_path  # noqa: E402


def region_map(sj):
    if "regions" not in sj:
        die("the subject has no region map: write it with scripts/auto_parts.py first")
    reg = cv2.imread(str(subject_path(sj, sj["regions"])), cv2.IMREAD_UNCHANGED)
    if reg is None:
        die(f"cannot read the region map {sj['regions']}")
    return reg.astype(np.int32)


def tolerant(a, b):
    wl = 1.0 if min(np.hypot(a[1], a[2]), np.hypot(b[1], b[2])) < 6 else 0.4
    return float(np.sqrt((wl * (a[0] - b[0])) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2))


def cmd_check(a):
    try:
        hints = json.loads(Path(a.hints).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"cannot read {a.hints}: {e}")
    sj = load_subject(a.subject)
    reg = region_map(sj)
    img, alpha = load_rgba(subject_path(sj, sj["image"]))
    L = lab(img)
    h, w = alpha.shape
    owner = {int(i): p["name"] for p in sj["parts"] for i in p.get("regions", [])}
    rows, marked = [], 0
    for p in hints.get("parts", []):
        cols = []
        boxes = p.get("boxes", []) + ([p["box"]] if "box" in p else [])
        for x, y in p.get("at", []):
            x, y = int(x), int(y)
            row = {"part": p["name"], "at": [x, y]}
            if not (0 <= y < h and 0 <= x < w):
                row["mark"] = "outside the picture"
            else:
                c = np.median(L[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3), axis=0)
                row.update({"region": int(reg[y, x]), "now": owner.get(int(reg[y, x]), "-"),
                            "lab": [round(float(v)) for v in c]})
                if alpha[y, x] < 0.5:
                    row["mark"] = "outside the figure"
                elif boxes and not any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes):
                    row["mark"] = "outside its part's boxes"
                cols.append((row, c))
            rows.append(row)
        # a point far in colour from all the other points of its part is often on the thing beside the part
        if len(cols) >= 3:
            for row, c in cols:
                others = [cc for rr, cc in cols if rr is not row]
                if min(tolerant(c, cc) for cc in others) > 30 and "mark" not in row:
                    row["mark"] = "far in colour from the part's other points: check it"
    marked = sum("mark" in r for r in rows)
    emit({"points": rows, "marked": marked})
    sys.exit(1 if marked else 0)


def cmd_points(a):
    sj = load_subject(a.subject)
    reg = region_map(sj)
    img, alpha = load_rgba(subject_path(sj, sj["image"]))
    L = lab(img)
    boxes = ndi.find_objects(reg)
    out = []
    for i in a.regions:
        if not (0 < i <= len(boxes)) or boxes[i - 1] is None:
            out.append({"region": i, "error": "no such region"})
            continue
        sl = boxes[i - 1]
        m = (reg[sl] == i).astype(np.uint8)
        d = cv2.distanceTransform(np.pad(m, 1), cv2.DIST_L2, 3)[1:-1, 1:-1]
        y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        x, y = int(sl[1].start + x), int(sl[0].start + y)
        out.append({"region": i, "at": [x, y], "lab": [round(float(v)) for v in L[y, x]]})
    emit({"points": out})


def _deepest(mask, n, min_area):
    """The point deepest inside each of the n largest patches of a mask: [(x, y, area)]."""
    k, cc, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = []
    for c in (np.argsort(-st[1:, cv2.CC_STAT_AREA])[:n] + 1 if k > 1 else []):
        if st[c, cv2.CC_STAT_AREA] < min_area:
            break
        d = cv2.distanceTransform(np.pad((cc == c).astype(np.uint8), 1), cv2.DIST_L2, 3)[1:-1, 1:-1]
        y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        out.append((int(x), int(y), int(st[c, cv2.CC_STAT_AREA])))
    return out


def cmd_pick(a):
    img, alpha = load_rgba(a.image)
    h, w = alpha.shape
    try:
        x0, y0, x1, y1 = (int(round(float(v))) for v in a.box.split(","))
    except ValueError:
        die("the box is x0,y0,x1,y1")
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        die("the box is empty or outside the picture")
    L = lab(img[y0:y1, x0:x1])
    on = alpha[y0:y1, x0:x1] > 0.9
    if a.like or a.near:
        if a.like:
            px, py = (int(round(float(v))) for v in a.like.split(","))
            if not (0 <= py < h and 0 <= px < w):
                die("the --like point is outside the picture")
            Lf = lab(img[max(0, py - 3):py + 4, max(0, px - 3):px + 4])
            targets = [np.median(Lf.reshape(-1, 3), axis=0)]
        else:
            targets = [np.array([float(v) for v in a.near.split(",")], np.float32)]
    else:
        # the box's main colours: k-means on its figure pixels, the clusters holding at least a tenth of it
        px = L[on]
        if len(px) < 50:
            die("the box holds almost none of the figure")
        sample = px[np.random.default_rng(0).choice(len(px), min(len(px), 20000), replace=False)].astype(np.float32)
        cv2.setRNGSeed(0)
        _, lbl, cen = cv2.kmeans(sample, 4, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3,
                                 cv2.KMEANS_PP_CENTERS)
        share = np.bincount(lbl.ravel(), minlength=4) / len(sample)
        targets = [cen[i] for i in np.argsort(-share) if share[i] >= 0.1]
    out = []
    for t in targets:
        c_ = float(np.hypot(t[1], t[2]))
        wl = 1.0 if c_ < 6 else 0.4
        d = np.sqrt((wl * (L[..., 0] - t[0])) ** 2 + (L[..., 1] - t[1]) ** 2 + (L[..., 2] - t[2]) ** 2)
        m = on & (d < a.tol)
        pts = [{"at": [x + x0, y + y0], "lab": [round(float(v)) for v in L[y, x]], "patch_px": ar}
               for x, y, ar in _deepest(m, a.n, 20)]
        out.append({"colour": [round(float(v)) for v in t], "points": pts} if pts else
                   {"colour": [round(float(v)) for v in t], "points": [], "note": "no patch of this colour in the box"})
    emit({"box": [x0, y0, x1, y1], "colours": out})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("hints")
    c.add_argument("subject")
    p = sub.add_parser("points")
    p.add_argument("subject")
    p.add_argument("regions", type=int, nargs="+")
    k = sub.add_parser("pick")
    k.add_argument("image")
    k.add_argument("box", help="x0,y0,x1,y1")
    g = k.add_mutually_exclusive_group()
    g.add_argument("--like", help="x,y: the colour under this point")
    g.add_argument("--near", help="L,a,b: this colour")
    k.add_argument("--tol", type=float, default=12.0, help="how near a colour counts (lightness counts less)")
    k.add_argument("-n", type=int, default=1, help="points per colour, from its largest patches")
    a = ap.parse_args()
    {"check": cmd_check, "points": cmd_points, "pick": cmd_pick}[a.cmd](a)


if __name__ == "__main__":
    main()
