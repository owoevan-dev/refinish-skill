#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Cut a figure out of a picture that has a background: the figure as a cut-out for the figure styles, and the
background with the figure's place filled, so each can be finished on its own and the figure put back where it was.

Usage:
  python scripts/cutout.py PICTURE.png OUTLINE.json OUT_DIR [--trimap TRIMAP.png]

OUTLINE.json (written by whoever looked at the picture; references/cutout.md):
  {"outline": [[[x, y], ...], ...],   polygons round the figure and everything that goes with it (a held prop, a
                                      wing, a horn), each within about `band` px of the real edge, outside it
   "band": 16,                        px: how far either side of the outline the colours decide
   "bands": [{"box": [x0, y0, x1, y1], "band": 8}],   another band inside a box
   "holes": [[[x, y], ...], ...],     polygons inside the outline that are background (the gap between the legs,
                                      an arm's loop), each within about `band` px of the real edge, inside it
   "keep": [[x, y], ...],             points sure to be figure (a strand, a strap, a thin prop)
   "drop": [[x, y], ...]}             points sure to be background (a speck of sky between strands)
--trimap: a picture the user painted, the picture's size: white is figure, black is background, mid grey is left to
the colours. It overrides everything else where it is not grey.

How it decides. Inside the outline, more than three bands in (halfway in for a small piece such as a horn), is sure
figure; outside it, more than one band out, is sure background. GrabCut (OpenCV; Rother, Kolmogorov and Blake 2004)
learns a colour model of each from those, then cuts the zone between them where the cut is cheapest: along strong
changes of colour, round what looks like neither side. A hole is outlined the same way from the other side: its middle
is sure background and its edge is decided by colour, so a gap whose colour is also the figure's (a purple sky behind
purple hair) still comes out. A point makes only its own spot sure and opens the other side's sure part round it
(three bands for a drop point, two for a keep point) to the colours; it never spreads by colour, since a colour
shared by the figure and the background is what fools a magic wand.
Holes are filled only when small; a larger enclosed area, such as the gap between the legs or the loop of a handle,
keeps the colours' decision. The edge is softened by half a pixel and its colour taken from just inside it, so no
background colour fringes the cut-out.

Writes, in OUT_DIR:
  figure.png      the figure as a cut-out (RGBA, the picture's size and place)
  background.png  the picture with the figure's place filled from round it, for a background finished on its own (the
                  figure covers that place again)
  cutout.json     the settings used, the figure's box and share, and the doubts
  review.jpg      the outline (cyan) and the cut (magenta) on the picture, the cut-out on green, each doubt enlarged
Prints JSON: the files, the figure's box and share, and "doubts", the places to look at first.
Exit codes: 0 done, 1 done with doubts, 2 bad input.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import die, emit, load_rgba, save_rgba  # noqa: E402
from _lines import meanshift  # noqa: E402
from auto_parts import disk, nearest  # noqa: E402

SURE_IN = 3            # bands inside the outline that are sure figure
CLOSE = 12.0           # Lab: a cut with less between the colours either side may have wandered
ITERS = 6              # GrabCut's rounds
GREEN = (60, 200, 120)


def polygons(h, w, polys):
    m = np.zeros((h, w), np.uint8)
    for p in polys:
        if len(p) >= 3:
            cv2.fillPoly(m, [np.int32(np.round(np.asarray(p, np.float32)))], 1)
    return m > 0


def band_map(h, w, spec):
    """Every pixel's band: the default, or a box's own."""
    B = np.full((h, w), float(spec.get("band", 16)), np.float32)
    for b in spec.get("bands", []):
        x0, y0, x1, y1 = (int(v) for v in b["box"])
        B[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = float(b["band"])
    return B


def push_pull_fill(img, hole):
    """The hole filled with the colours round it, smoothly (a pyramid: averaged down, filled up)."""
    levels = [(img * (~hole)[..., None], (~hole).astype(np.float32))]
    while min(levels[-1][1].shape) > 8:
        c, w_ = levels[-1]
        levels.append((cv2.pyrDown(c), cv2.pyrDown(w_)))
    c, w_ = levels[-1]
    filled = c / np.maximum(w_[..., None], 1e-6)
    filled[w_ < 1e-6] = c.reshape(-1, 3).sum(0) / max(float(w_.sum()), 1e-6)
    for c, w_ in reversed(levels[:-1]):
        up = cv2.pyrUp(filled, dstsize=(c.shape[1], c.shape[0]))
        filled = np.where(w_[..., None] > 1e-3, c / np.maximum(w_[..., None], 1e-6), up)
        filled = np.where(w_[..., None] > 0.999, filled, w_[..., None] * filled + (1 - w_[..., None]) * up)
    out = img.copy()
    out[hole] = filled[hole]
    return out


def boxes_of(mask, grow, min_area):
    """Boxes round the clusters of a mask (pieces within `grow` px joined), the larger first."""
    if not mask.any():
        return []
    joined = cv2.dilate(mask.astype(np.uint8), disk(grow)) > 0
    lab_, _ = ndi.label(joined)
    out = []
    for i, sl in enumerate(ndi.find_objects(lab_), 1):
        area = int((mask[sl] & (lab_[sl] == i)).sum())
        if area >= min_area:
            out.append(([int(sl[1].start), int(sl[0].start), int(sl[1].stop), int(sl[0].stop)], area))
    return sorted(out, key=lambda t: -t[1])


def review(img, out_dir, rough, fig, alpha, doubts):
    h, w = fig.shape
    src = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    lined = src.copy()
    for m, col in ((rough, (0, 230, 255)), (fig, (255, 0, 200))):
        e = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        lined[e] = col
    cut = img * alpha[..., None] + np.array(GREEN, np.float32) / 255 * (1 - alpha[..., None])
    cut = (np.clip(cut, 0, 1) * 255).astype(np.uint8)
    H = 900
    k = H / h
    big = [cv2.resize(t, (max(1, int(w * k)), H), interpolation=cv2.INTER_AREA) for t in (lined, cut)]
    tiles = []
    for i, d in enumerate(doubts[:6], 1):
        x0, y0, x1, y1 = d["box"]
        cv2.rectangle(big[0], (int(x0 * k), int(y0 * k)), (int(x1 * k), int(y1 * k)), (255, 230, 0), 2)
        cv2.putText(big[0], str(i), (int(x0 * k) + 3, int(y0 * k) + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255, 230, 0), 2, cv2.LINE_AA)
        m = max(24, (x1 - x0) // 3, (y1 - y0) // 3)
        X0, Y0, X1, Y1 = max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m)
        pair = np.hstack([lined[Y0:Y1, X0:X1], np.full((Y1 - Y0, 3, 3), 255, np.uint8), cut[Y0:Y1, X0:X1]])
        s = min(440 / pair.shape[1], 200 / pair.shape[0], 6.0)
        pair = cv2.resize(pair, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
        tile = np.full((224, 444, 3), 255, np.uint8)
        tile[:pair.shape[0], :pair.shape[1]] = pair
        cv2.putText(tile, str(i), (4, 218), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
        tiles.append(tile)
    gap = np.full((H, 8, 3), 255, np.uint8)
    row = np.hstack([big[0], gap, big[1]])
    if tiles:
        col = np.vstack(tiles)[:H]
        col = np.pad(col, ((0, H - col.shape[0]), (0, 0), (0, 0)), constant_values=255)
        row = np.hstack([row, gap, col])
    path = out_dir / "review.jpg"
    cv2.imwrite(str(path), cv2.cvtColor(row, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture")
    ap.add_argument("outline", help="the outline file (references/cutout.md)")
    ap.add_argument("out_dir")
    ap.add_argument("--trimap", help="a painted picture: white figure, black background, grey left to the colours")
    a = ap.parse_args()
    try:
        spec = json.loads(Path(a.outline).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"cannot read the outline {a.outline}: {e}")
    polys = spec.get("outline") or []
    if polys and np.asarray(polys[0]).ndim == 1:          # one polygon given without the outer list
        polys = [polys]
    img, _ = load_rgba(a.picture)
    h, w = img.shape[:2]
    holes = spec.get("holes") or []
    if holes and np.asarray(holes[0]).ndim == 1:
        holes = [holes]
    rough = polygons(h, w, polys) & ~polygons(h, w, holes)
    if rough.sum() < 1000:
        die("the outline encloses (almost) nothing: give one or more polygons round the figure as [[x, y], ...]")
    B = band_map(h, w, spec)
    band = float(spec.get("band", 16))

    # 1. sure figure, sure background, and the zone between. Sure figure starts three bands in, or halfway in for a
    # piece that is not six bands across. A drop point opens the sure figure round it, a keep point the sure background.
    d_in = cv2.distanceTransform(rough.astype(np.uint8), cv2.DIST_L2, 5)
    d_out = cv2.distanceTransform((~rough).astype(np.uint8), cv2.DIST_L2, 5)
    comp, nc = ndi.label(rough)
    dmax = np.concatenate([[0.0], np.asarray(ndi.maximum(d_in, comp, range(1, nc + 1)), np.float32)])
    thr = np.minimum(SURE_IN * B, 0.5 * dmax[comp])
    sure_fg = rough & (d_in > thr)
    bgc, nb = ndi.label(~rough)                              # the background and each hole: halfway in for a narrow one
    bmax = np.concatenate([[0.0], np.asarray(ndi.maximum(d_out, bgc, range(1, nb + 1)), np.float32)])
    sure_bg = ~rough & (d_out > np.minimum(B, 0.5 * bmax[bgc]))
    seeds = {"keep": np.zeros((h, w), np.uint8), "drop": np.zeros((h, w), np.uint8)}
    dots = {"keep": np.zeros((h, w), np.uint8), "drop": np.zeros((h, w), np.uint8)}
    for key in seeds:
        for x, y in spec.get(key, []):
            x, y = int(round(x)), int(round(y))
            if not (0 <= x < w and 0 <= y < h):
                die(f"the {key} point {[x, y]} is outside the picture ({w} x {h})")
            cv2.circle(seeds[key], (x, y), int(round((SURE_IN if key == "drop" else 2) * B[y, x])), 1, -1)
            cv2.circle(dots[key], (x, y), max(2, int(round(0.25 * B[y, x]))), 1, -1)
    seeds = {k: v > 0 for k, v in seeds.items()}
    dots = {k: v > 0 for k, v in dots.items()}
    sure_fg &= ~seeds["drop"]
    sure_bg &= ~seeds["keep"]
    painted = None
    if a.trimap:
        t = cv2.imread(a.trimap, cv2.IMREAD_GRAYSCALE)
        if t is None or t.shape != (h, w):
            die(f"the trimap must be a picture of the same size as {a.picture} ({w} x {h})")
        painted = (t > 200, t < 55)

    # 2. GrabCut decides the zone by colour, the sure parts, the points and the painting fixed
    m = np.full((h, w), cv2.GC_BGD, np.uint8)
    m[~sure_bg & ~rough] = cv2.GC_PR_BGD
    m[~sure_fg & rough] = cv2.GC_PR_FGD
    m[sure_fg] = cv2.GC_FGD
    m[seeds["keep"] & ~rough & (m == cv2.GC_BGD)] = cv2.GC_PR_BGD
    m[dots["keep"]] = cv2.GC_FGD
    m[dots["drop"]] = cv2.GC_BGD
    if painted is not None:
        m[painted[0]] = cv2.GC_FGD
        m[painted[1]] = cv2.GC_BGD
    # GrabCut on the figure's surroundings only: the colours far off say nothing about this edge
    live = cv2.dilate((m != cv2.GC_BGD).astype(np.uint8), disk(int(2 * band))) > 0
    ys, xs = np.nonzero(live)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    bgr8 = cv2.cvtColor((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)
    mc = np.ascontiguousarray(m[y0:y1, x0:x1])
    if not ((mc == cv2.GC_BGD) | (mc == cv2.GC_PR_BGD)).any() or not ((mc == cv2.GC_FGD) | (mc == cv2.GC_PR_FGD)).any():
        die("the outline leaves no background or no figure to learn colours from: draw it round the figure, "
            "inside the picture")
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(np.ascontiguousarray(bgr8[y0:y1, x0:x1]), mc, None, bgd, fgd, ITERS, cv2.GC_INIT_WITH_MASK)
    m[y0:y1, x0:x1] = mc
    fig = (m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD)

    # 3. clean up: keep the pieces joined to the sure figure or to a keep point; fill small holes only
    lab_, _ = ndi.label(fig)
    anchor = sure_fg | dots["keep"] | (painted[0] if painted is not None else False)
    keep_ids = set(np.unique(lab_[anchor & fig]).tolist()) - {0}
    fig = np.isin(lab_, list(keep_ids))
    enclosed = ndi.binary_fill_holes(fig) & ~fig
    hl, nh = ndi.label(enclosed)
    if nh:
        sizes = ndi.sum(enclosed, hl, range(1, nh + 1))
        small = np.isin(hl, 1 + np.flatnonzero(sizes < max(30.0, 0.0002 * h * w)))
        fig |= small & ~(dots["drop"] | (painted[1] if painted is not None else False))
    if not fig.any():
        die("nothing was kept as figure: the outline or the painting leaves no sure figure")

    # 4. the cut-out: the edge softened by half a pixel, its colour taken from just inside it
    inner = cv2.erode(fig.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    alpha = np.clip(cv2.GaussianBlur(fig.astype(np.float32), (0, 0), 0.6), 0, 1)
    alpha[inner] = 1.0
    alpha[~(cv2.dilate(fig.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)] = 0.0
    if inner.any():
        _, near = nearest(np.where(inner, np.arange(1, h * w + 1, dtype=np.int64).reshape(h, w), 0))
        col = img.reshape(-1, 3)[np.clip(near.ravel() - 1, 0, h * w - 1)].reshape(h, w, 3)
        fig_rgb = np.where(inner[..., None], img, col)
    else:
        fig_rgb = img
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    save_rgba(out_dir / "figure.png", fig_rgb, alpha)
    hole = cv2.dilate(fig.astype(np.uint8), disk(3)) > 0
    save_rgba(out_dir / "background.png", push_pull_fill(img, hole), np.ones((h, w), np.float32))

    # 5. doubts: stretches of the cut with nearly one colour either side, areas cut deep inside the outline
    doubts = []
    smooth8 = cv2.cvtColor((np.clip(meanshift(img, 6, 12), 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2Lab)
    Ls = smooth8.astype(np.float32)
    Ls[..., 0] *= 100.0 / 255.0                              # 8-bit Lab: L to 0..100, a and b round 128 as they are
    f8 = fig.astype(np.uint8)
    ring_in = (cv2.erode(f8, disk(2)) > 0) & ~(cv2.erode(f8, disk(5)) > 0)
    ring_out = (cv2.dilate(f8, disk(5)) > 0) & ~(cv2.dilate(f8, disk(2)) > 0)
    cut_px = fig & ~inner
    if ring_in.any() and ring_out.any():
        idx = np.arange(1, h * w + 1, dtype=np.int64).reshape(h, w)
        _, ni = nearest(np.where(ring_in, idx, 0))
        _, no = nearest(np.where(ring_out, idx, 0))
        ys_, xs_ = np.nonzero(cut_px)
        flat = Ls.reshape(-1, 3)
        dE = np.linalg.norm(flat[ni[ys_, xs_] - 1] - flat[no[ys_, xs_] - 1], axis=1)
        low = np.zeros((h, w), bool)
        low[ys_[dE < CLOSE], xs_[dE < CLOSE]] = True
        T, cand = int(6 * band), []
        for ty in range(0, h, T):                            # tiles of six bands: a stretch two bands long counts
            for tx in range(0, w, T):
                yy_, xx_ = np.nonzero(low[ty:ty + T, tx:tx + T])
                if len(yy_) >= 2 * band:
                    cand.append((len(yy_), [tx + int(xx_.min()), ty + int(yy_.min()), tx + int(xx_.max()) + 1,
                                            ty + int(yy_.max()) + 1]))
        for _n, box in sorted(cand, key=lambda c: -c[0])[:4]:
            doubts.append({"box": box, "kind": "close colours",
                           "why": "nearly one colour either side of the cut here, so it may have wandered: look; "
                                  "a keep or drop point, a narrower band in a box, or a painted trimap"})
    deep = rough & ~fig & (d_in > 1.5 * B)
    dl, _ = ndi.label(deep)
    deep &= ~np.isin(dl, np.unique(dl[seeds["drop"]]))          # a gap asked for with a drop point is no doubt
    for box, _area in boxes_of(deep, 3, max(60.0, 4 * band * band))[:4]:
        doubts.append({"box": box, "kind": "cut deep inside the outline",
                       "why": "an area well inside the outline went to the background: right for a gap (between "
                              "the legs, inside a handle), wrong for a part coloured like the background (a keep "
                              "point there)"})
    edges = {"top": fig[0].any(), "bottom": fig[-1].any(), "left": fig[:, 0].any(), "right": fig[:, -1].any()}
    yy, xx = np.nonzero(fig)
    rv = review(img, out_dir, rough, fig, alpha, doubts)
    res = {"figure": str(out_dir / "figure.png"), "background": str(out_dir / "background.png"),
           "review": str(rv), "box": [int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1],
           "share": round(float(fig.mean()), 4),
           "settings": {"band": band, "bands": spec.get("bands", []), "keep": len(spec.get("keep", [])),
                        "drop": len(spec.get("drop", [])), "trimap": bool(a.trimap)},
           "frame_cuts_figure": [k_ for k_, v in edges.items() if v], "doubts": doubts}
    (out_dir / "cutout.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    emit(res)
    sys.exit(1 if doubts else 0)


if __name__ == "__main__":
    main()
