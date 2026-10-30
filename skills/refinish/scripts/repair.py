#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Repair a source picture's defects by code, without changing its style: a cut-out's fringe, stray specks, gaps in
its line art, colour that ran from one material into the next.

Usage:
  python scripts/repair.py PICTURE.png OUT.png [--fix halo,specks,lines,bleed] [--subject SUBJECT.json]
                           [--upscaled N] [--dry-run]

  halo    a cut-out's edge keeps a light or dark fringe of the background it was cut from: the edge's colour is
          taken from just inside it, and where the fringe is strong the matte is choked by a pixel
  specks  small blobs of a colour foreign to the flat area round them (rendering noise, stray dots) are filled from
          their surroundings; lines, the protected features and anything in a busy area are left alone
  lines   gaps in the line art: two line ends facing each other across a short gap, or a line end facing a line, are
          joined with a stroke of the line's own colour and width
  bleed   colour that ran across a part's edge into its neighbour: near a part's boundary, pixels in the neighbour's
          colour and not their own part's are repainted from their part (needs --subject)

By default every repair that applies is made (bleed only with a subject). --dry-run reports without writing.
The review picture (OUT.repair.jpg) marks every change: halo blue, specks red, lines green, bleed magenta.
Prints JSON: per repair, how much it found and changed, and where.
Exit codes: 0 done, 2 bad input.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import Units, die, emit, lab, load_rgba, over, rgb, save_rgba  # noqa: E402

REPAIRS = ("halo", "specks", "lines", "bleed")


# --------------------------------------------------------------------------------------------------------------- halo

def fix_halo(img, alpha, U, out_alpha):
    """The cut-out's edge: semi-transparent pixels and the outermost opaque ring take the colour of the nearest pixel
    well inside the figure, so no trace of the old background's colour is left round it."""
    h, w = alpha.shape
    solid = alpha > 0.98
    band = max(1, int(round(U.len(0.6))))
    inner = cv2.erode(solid.astype(np.uint8), np.ones((2 * band + 1, 2 * band + 1), np.uint8)) > 0
    if inner.sum() < 100:
        return img, {"found": False, "why": "no figure inside the edge"}
    edge = (alpha > 0.02) & ~inner
    dist, lbl = cv2.distanceTransformWithLabels((~inner).astype(np.uint8), cv2.DIST_L2, 5,
                                                labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(inner)
    lut = np.zeros((lbl.max() + 1, 3), np.float32)
    lut[lbl[ys, xs]] = img[ys, xs]
    ref = lut[lbl]
    L, Lr = lab(img)[..., 0], lab(ref)[..., 0]
    d = (L - Lr)[edge & (alpha > 0.3)]
    if not d.size:
        return img, {"found": False}
    light, dark = float((d > 15).mean()), float((d < -15).mean())
    sign = 1 if light >= dark else -1
    share = max(light, dark)
    found = share > 0.2                                     # a fringe runs round much of the edge, one way
    out = img.copy()
    semi = edge & ~solid
    out[semi] = ref[semi]                                   # the semi-transparent edge: colour from inside
    ring = edge & solid & (np.abs(L - Lr) > 10) & (np.sign(L - Lr) == sign)
    if found:
        out[ring] = ref[ring]
    if share > 0.5:                                         # a wide fringe: the matte choked by a pixel
        out_alpha[:] = np.minimum(out_alpha, cv2.erode(out_alpha, np.ones((3, 3), np.uint8)) * 0.5 + out_alpha * 0.5)
    changed = semi | (ring if found else np.zeros_like(ring))
    return out, {"found": found, "fringe": ("light" if sign > 0 else "dark") if found else None,
                 "edge_share": round(share, 3), "changed_px": int(changed.sum()), "_mask": changed}


# ------------------------------------------------------------------------------------------------------------- specks

def fix_specks(img, alpha, U, protect, line, face=None, max_area=None, de=12.0, flat=4.0):
    """Small blobs foreign to a flat area: each blob's colour is far from the area's median, the ring round it is
    flat (a speck in a flat field, not a sparkle in a detailed one), and it is not a line or a protected feature.
    A dark dot reads as line art, and on a face it is a feature (a nostril, a mole): dark dots are taken only when
    the face is known (`face`, from a subject) and only off it."""
    within = alpha > 0.5
    # a speck is at most a few u across, and never less than a few pixels: on a small picture a unit is under a
    # pixel, and a 3 x 3 dot is still a speck. The median that tells it from its area reaches past it
    max_area = max_area or max(16.0, U.area(4.0))
    k = max(5, int(round(max(U.len(2.5), 2.2 * np.sqrt(max_area)))) | 1)
    Lab_ = lab(img)
    q8 = np.clip(np.stack([Lab_[..., 0] * 2.55, Lab_[..., 1] + 128, Lab_[..., 2] + 128], -1), 0, 255).astype(np.uint8)
    m8 = cv2.medianBlur(q8, k).astype(np.float32)
    med = np.stack([m8[..., 0] / 2.55, m8[..., 1] - 128, m8[..., 2] - 128], -1)
    diff = np.linalg.norm(Lab_ - med, axis=-1)
    # the line finder takes any small dark-against-light mark for line art; a small isolated mark of the line art is
    # set free when it is not a line's colour: more colourful than its surroundings (line art is dark and dull), or
    # anywhere off a known face
    n_, cc_, st_, _ = cv2.connectedComponentsWithStats(line.astype(np.uint8), connectivity=8)
    dots = st_[:, cv2.CC_STAT_AREA] <= 3 * max_area
    dots[0] = False
    chroma = np.hypot(Lab_[..., 1], Lab_[..., 2])
    c_med = np.hypot(med[..., 1], med[..., 2])
    vivid = np.bincount(cc_.ravel(), weights=(chroma - c_med).ravel(), minlength=n_) / np.maximum(st_[:, 4], 1) > 12
    free = dots & vivid
    if face is not None:
        free |= dots                                    # (off the face, checked below)
        line = line & ~(free[cc_] & ~face)
    else:
        line = line & ~free[cc_]
    cand = (diff > de) & within & ~line & ~protect
    n, cc, st, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), connectivity=8)
    out = img.copy()
    fixed = np.zeros(alpha.shape, bool)
    places = []

    for i in range(1, n):
        a_ = st[i, cv2.CC_STAT_AREA]
        if a_ > max_area:
            continue
        x, y, bw, bh = st[i, :4]
        if max(bw, bh) > 3 * max(1, min(bw, bh)) and max(bw, bh) > 6:
            continue                                        # (elongated: a stroke, not a speck)
        pad = max(3, int(round(U.len(1.5))))
        y0, y1, x0, x1 = max(0, y - pad), min(alpha.shape[0], y + bh + pad), max(0, x - pad), min(alpha.shape[1], x + bw + pad)
        blob = cc[y0:y1, x0:x1] == i
        grown = cv2.dilate(blob.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        if (grown & ~within[y0:y1, x0:x1]).any() or (grown & line[y0:y1, x0:x1]).any():
            continue                                        # (at the outline or against a line: a corner, not a speck)
        ring = grown & ~blob & within[y0:y1, x0:x1]
        if ring.sum() < 8:
            continue
        rc = Lab_[y0:y1, x0:x1][ring]
        rmed = np.median(rc, axis=0)
        spread = float(np.percentile(np.linalg.norm(rc - rmed, axis=1), 90))
        if spread > flat:
            continue                                        # (a busy area or a meeting of tones: detail, not a speck)
        step = float(np.linalg.norm(np.median(Lab_[y0:y1, x0:x1][blob], axis=0) - rmed))
        if step < max(de, 4 * spread):
            continue                                        # (barely off its surroundings: a soft step, not a speck)
        fill = np.median(img[y0:y1, x0:x1][ring], axis=0)
        sub = out[y0:y1, x0:x1]
        sub[blob] = fill
        fixed[y0:y1, x0:x1] |= blob
        places.append([int(x), int(y), int(x + bw), int(y + bh)])
    return out, {"found": len(places), "changed_px": int(fixed.sum()), "places": places[:20], "_mask": fixed}


# -------------------------------------------------------------------------------------------------------------- lines

def thin(mask):
    """Zhang-Suen thinning (1984), vectorised: the line art's centre lines, one pixel wide."""
    m = np.pad(mask.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p = [m[1:-1, 1:-1], m[:-2, 1:-1], m[:-2, 2:], m[1:-1, 2:], m[2:, 2:], m[2:, 1:-1], m[2:, :-2],
                 m[1:-1, :-2], m[:-2, :-2]]
            p2, p3, p4, p5, p6, p7, p8, p9 = p[1:]
            b = p2.astype(np.int32) + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            a = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32) for i in range(8))
            if step == 0:
                c = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                c = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            rm = (p[0] == 1) & (b >= 2) & (b <= 6) & (a == 1) & c
            if rm.any():
                m[1:-1, 1:-1][rm] = 0
                changed = True
        if not changed:
            return m[1:-1, 1:-1].astype(bool)


def fix_lines(img, alpha, U, line, max_gap=None, max_turn=30.0):
    """Gaps in the line art closed: a line end facing another line end, or facing a line's side, across a gap no
    longer than `max_gap`, joined by a stroke of the line's colour and width. A gap between ends that point away from
    each other is left: it is drawn so (a strand's tip, a fold that stops)."""
    within = alpha > 0.5
    max_gap = max_gap or U.len(5.0)
    h, w = alpha.shape
    width = cv2.distanceTransform(line.astype(np.uint8), cv2.DIST_L2, 3)
    sk = thin(line & within)

    def count(s):
        return sum(np.roll(np.roll(s, dy, 0), dx, 1).astype(np.int32) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                   if dy or dx)

    # pruning: a thinned thick line forks at a flat end and grows spurs at its corners; ends are taken off a few
    # times over, which removes the forks and spurs and leaves each real stroke a little short of its tip
    wd = float(np.median(width[sk])) if sk.any() else 1.0
    n_prune = max(2, int(round(2 * wd)))
    for _ in range(n_prune):
        e = sk & (count(sk) == 1)
        if not e.any():
            break
        sk &= ~e
    ends = np.argwhere(sk & (count(sk) == 1))
    if not len(ends):
        return img, {"found": 0, "changed_px": 0, "_mask": np.zeros(alpha.shape, bool)}
    # each end's direction, from its stroke a few steps back; then its tip: walked out along that direction to where
    # the drawn line stops
    back = max(4, int(round(U.len(2.0))))
    dirs, tips = [], []
    for (y, x) in ends:
        y0, y1, x0, x1 = max(0, y - back), min(h, y + back + 1), max(0, x - back), min(w, x + back + 1)
        ys, xs = np.nonzero(sk[y0:y1, x0:x1])
        v = np.array([x - (xs.mean() + x0), y - (ys.mean() + y0)], np.float64)
        n_ = np.hypot(*v)
        v = v / n_ if n_ > 0.5 else np.zeros(2)
        q = np.array([x, y], np.float64)
        if v.any():
            for _ in range(2 * (n_prune + int(2 * wd) + 2)):
                nq = q + v * 0.5
                qx, qy = int(round(nq[0])), int(round(nq[1]))
                if not (0 <= qx < w and 0 <= qy < h) or not line[qy, qx]:
                    break
                q = nq
        dirs.append(v)
        tips.append(q)
    dirs = np.array(dirs)
    cos_t = np.cos(np.radians(max_turn))
    out = img.copy()
    drawn = np.zeros((h, w), np.uint8)
    joins = []
    used = set()
    pts = np.array(tips)                                   # (x, y)
    for i in range(len(ends)):
        if i in used or not dirs[i].any():
            continue
        best, target = None, None
        d = pts - pts[i]
        dist = np.hypot(d[:, 0], d[:, 1])
        for j in np.argsort(dist):
            if j == i or j in used or dist[j] < 1.5 or dist[j] > max_gap:
                continue
            u = d[j] / dist[j]
            if dirs[i] @ u > cos_t and dirs[j].any() and dirs[j] @ -u > cos_t:
                best, target = j, pts[j]
                break
        if target is None:                                  # facing a line's side: walk the ray to the first line
            for t in np.arange(1.5, max_gap, 0.5):
                q = pts[i] + dirs[i] * t
                qx, qy = int(round(q[0])), int(round(q[1]))
                if not (0 <= qx < w and 0 <= qy < h) or not within[qy, qx]:
                    break
                if line[qy, qx]:
                    target = q if t >= 2.0 else None       # (a line touched at once: no gap)
                    break
        if target is None:
            continue
        a0, a1 = pts[i], target
        seg = np.zeros((h, w), np.uint8)
        cv2.line(seg, (int(a0[0]), int(a0[1])), (int(a1[0]), int(a1[1])), 1, 1)
        if (seg.astype(bool) & ~within).any():
            continue
        thick = max(1, int(round(2 * width[ends[i][0], ends[i][1]] - 1)))   # (the stroke's width, from its centre)
        r = max(2, thick)
        y0, y1, x0, x1 = (max(0, int(a0[1]) - r), min(h, int(a0[1]) + r + 1), max(0, int(a0[0]) - r),
                          min(w, int(a0[0]) + r + 1))
        near = line[y0:y1, x0:x1]
        colour = np.median(img[y0:y1, x0:x1][near], axis=0) if near.any() else np.zeros(3, np.float32)
        stroke = np.zeros((h, w), np.uint8)
        cv2.line(stroke, (int(a0[0]), int(a0[1])), (int(round(a1[0])), int(round(a1[1]))), 255, thick, cv2.LINE_AA)
        k = stroke.astype(np.float32)[..., None] / 255
        out = out * (1 - k) + colour * k
        drawn |= stroke
        used.add(i)
        if best is not None:
            used.add(best)
        joins.append([int(a0[0]), int(a0[1]), int(round(a1[0])), int(round(a1[1]))])
    return out, {"found": len(joins), "changed_px": int((drawn > 0).sum()), "joins": joins[:20], "_mask": drawn > 0}


# -------------------------------------------------------------------------------------------------------------- bleed

def fix_bleed(img, alpha, U, parts, names, line, protect, reach=None, margin=6.0):
    """Colour run across a part's edge: within `reach` of another part, a pixel nearer that part's colours than its
    own part's (by `margin`) is the neighbour's paint; it is repainted from its own part's pixels nearby."""
    within = alpha > 0.5
    reach = reach or U.len(4.0)
    Lab_ = lab(img)
    out = img.copy()
    fixed = np.zeros(alpha.shape, bool)
    moves = {}
    n = len(names)
    tones = {}
    for j in range(1, n + 1):
        m = (parts == j) & within & ~line
        if m.sum() < 200:
            continue
        v = Lab_[m]
        Ls = v[:, 0]
        cut = np.median(Ls)
        tones[j] = [np.median(v[Ls >= cut], axis=0), np.median(v[Ls < cut], axis=0)]

    def dist_to(j, px):
        return np.min(np.stack([np.linalg.norm(px - t, axis=-1) for t in tones[j]]), axis=0)

    r_ = int(np.ceil(reach))
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_ + 1, 2 * r_ + 1))
    # the figure's own outline band is left alone (its outline is line art the line finder does not see against the
    # transparent ground, and a strip of it given to the wrong part is the part map's mistake, not the paint's)
    rim = cv2.distanceTransform(within.astype(np.uint8), cv2.DIST_L2, 3) <= U.len(3.0)
    for j in tones:
        m = (parts == j) & within
        ring = (cv2.dilate(m.astype(np.uint8), disk) > 0) & ~m & within
        for k_ in np.unique(parts[ring]):
            if k_ == j or k_ not in tones:
                continue
            # only along the border with this neighbour, and only what runs in from that border; nothing darker than
            # both parts' shadows (a line the finder missed)
            mk = (parts == k_) & within
            dk = cv2.distanceTransform((~mk).astype(np.uint8), cv2.DIST_L2, 3)
            darkest = min(tones[j][1][0], tones[k_][1][0]) - 6
            band = m & (dk <= reach) & ~line & ~protect & ~rim & (Lab_[..., 0] > darkest)
            if not band.any():
                continue
            px = Lab_[band]
            own, other = dist_to(j, px), dist_to(k_, px)
            bad = (other + margin < own) & (other < 12)
            if not bad.any():
                continue
            sel = np.zeros(alpha.shape, bool)
            sel[band] = bad
            sel &= ~fixed
            n_, cc = cv2.connectedComponents(sel.astype(np.uint8), connectivity=8)
            touch = np.unique(cc[(dk <= 2.5) & sel])
            sel = np.isin(cc, touch[touch > 0])
            if sel.sum() < 4:
                continue
            good = (m & ~sel & ~line).astype(np.float32)
            sig = max(1.0, reach)
            num = np.stack([cv2.GaussianBlur(img[..., c] * good, (0, 0), sig) for c in range(3)], -1)
            den = cv2.GaussianBlur(good, (0, 0), sig)[..., None]
            fill = num / np.maximum(den, 1e-4)
            ok = sel & (den[..., 0] > 0.05)
            out[ok] = fill[ok]
            fixed |= ok
            key = f"{names[k_ - 1]} into {names[j - 1]}"
            moves[key] = moves.get(key, 0) + int(ok.sum())
    return out, {"found": len(moves), "changed_px": int(fixed.sum()),
                 "runs": [{"what": k, "px": v} for k, v in sorted(moves.items(), key=lambda t: -t[1])][:12],
                 "_mask": fixed}


# ---------------------------------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture")
    ap.add_argument("out")
    ap.add_argument("--fix", help=f"which repairs, comma-separated ({', '.join(REPAIRS)}; default all that apply)")
    ap.add_argument("--subject", help="the picture's subject file: the protected features kept, and bleed")
    ap.add_argument("--upscaled", type=int, default=None, help="how many times the picture was enlarged")
    ap.add_argument("--dry-run", action="store_true", help="report only")
    a = ap.parse_args()
    fixes = [f.strip() for f in a.fix.split(",")] if a.fix else [f for f in REPAIRS if f != "bleed" or a.subject]
    bad = [f for f in fixes if f not in REPAIRS]
    if bad:
        die(f"no repair {', '.join(bad)}: {', '.join(REPAIRS)}")
    if "bleed" in fixes and not a.subject:
        die("bleed needs --subject: the parts say which colour belongs where")
    img, alpha = load_rgba(a.picture)
    sj, parts, names = None, None, []
    if a.subject:
        from _style import load_subject
        from parts import load_or_build
        sj = load_subject(a.subject)
        img_s, alpha_s, parts = load_or_build(sj)
        if img_s.shape != img.shape:
            die(f"{a.picture} is not the subject's picture (sizes differ)")
        names = [p["name"] for p in sj["parts"]]
    up = a.upscaled or (sj.get("upscaled", 1) if sj else 1)
    U = Units(alpha, sj.get("head_px") if sj else None)
    from _lines import find_lines
    line = (find_lines(img, up) > 0.3) & (alpha > 0.5)
    protect = np.zeros(alpha.shape, bool)
    for p in (sj or {}).get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        protect[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    out, out_alpha = img.copy(), alpha.copy()
    report, marks = {}, {}
    for f in fixes:
        if f == "halo":
            out, r = fix_halo(out, alpha, U, out_alpha)
        elif f == "specks":
            face = None
            if sj is not None:
                from _core import ellipse_mask
                face = (ellipse_mask(*alpha.shape, sj.get("focal", [])) > 0.3) | protect
            out, r = fix_specks(out, alpha, U, protect, cv2.dilate(line.astype(np.uint8), np.ones((3, 3))) > 0, face)
        elif f == "lines":
            out, r = fix_lines(out, alpha, U, line)
        else:
            out, r = fix_bleed(out, alpha, U, parts, names, line, protect)
        marks[f] = r.pop("_mask", None)
        report[f] = r
    res = {"picture": a.picture, "repairs": report}
    if not a.dry_run:
        save_rgba(a.out, np.clip(out, 0, 1), out_alpha)
        rv = Path(a.out).with_suffix(".repair.jpg")
        view = over(out, out_alpha).astype(np.float32)
        for f, col in (("halo", (255, 120, 0)), ("specks", (0, 0, 255)), ("lines", (0, 200, 0)),
                       ("bleed", (255, 0, 255))):
            m = marks.get(f)
            if m is not None and m.any():
                edge = cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
                view[edge & ~m] = view[edge & ~m] * 0.3 + np.array(col, np.float32) * 0.7
        cv2.imwrite(str(rv), view.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 90])
        res.update({"out": a.out, "review": str(rv)})
    emit(res)


if __name__ == "__main__":
    main()
