#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Write a subject file without placing a sample: the figure's parts found, named and given kinds, the eyes and the
mouth boxed, the face made the focal area.

Usage:
  python scripts/auto_parts.py IMAGE.png SUBJECT.json [--upscaled N] [--head-px N] [--hints HINTS.json] [--like OTHER.json]

The parts are found the way a colourist reads a drawing: the areas the lines enclose (a ball rolled through the
picture, so a gap in a line does not let one area run into the next: trapped-ball filling), then the face (a
skin-coloured area with eyes in it), the eyes and the mouth inside it, the hair growing out from round the face, the
skin of the face's colour, and the rest grouped by colour into the clothes, each given the kind its colour and its
place suggest (references/subject-file.md, "Parts found automatically").

Writes SUBJECT.json, the region map it names (<subject>.regions.png: each pixel's region number) and three review
pictures: <subject>.auto.jpg (each part in false colour, each region's number, a grid in the picture's pixels),
<subject>.face.jpg (the face enlarged, with the boxes) and <subject>.sheet.jpg (every part on its own, in its own
colours: a material mixed into the wrong part shows there). With --hints (what whoever looked at the picture names:
points and rough boxes per part, the eyes and the mouth boxed; references/subject-file.md) the parts are those named,
cut out exactly. A part owns the regions in its "regions" list; fix a mistake by adding a point or a box and running
again, or by moving a region's number to another part's list. --like takes the names and the kinds of another subject
of the same character, so a set of pictures gets the same parts.
Prints JSON: the parts (kind, colour, share of the figure), the boxes, and "doubts", the places to look at first.
Exit codes: 0 done, 1 done with doubts, 2 bad input.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import Units, die, emit, lab, load_rgba, over  # noqa: E402
from _lines import find_lines  # noqa: E402

REGIONS_FORMAT = 1
# the review's part colours: Kelly's colours of maximum contrast (Kelly 1965), as RGB, white and black left out
KELLY = [(242, 243, 244), (243, 195, 0), (135, 86, 146), (243, 132, 0), (161, 202, 241), (190, 0, 50), (194, 178, 128),
         (132, 132, 130), (0, 136, 86), (230, 143, 172), (0, 103, 165), (249, 147, 121), (96, 78, 151), (246, 166, 0),
         (179, 68, 108), (220, 211, 0), (136, 45, 23), (141, 182, 0), (101, 69, 34), (226, 88, 34), (43, 61, 38)]


def disk(r):
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def nearest(labels):
    """For every pixel, the distance to the nearest labelled pixel (label > 0) and that pixel's label."""
    dist, near = cv2.distanceTransformWithLabels((labels == 0).astype(np.uint8), cv2.DIST_L2, 5,
                                                 labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(labels > 0)
    lut = np.zeros(near.max() + 1, labels.dtype)
    lut[near[ys, xs]] = labels[ys, xs]
    return dist, lut[near]


# ----------------------------------------------------------------------------------------------------------- regions

def trapped_ball(free, radii):
    """The areas the lines enclose: a ball of each radius in turn, the largest first, fills what it can reach without
    leaving the free pixels; where it cannot pass (a gap in a line narrower than the ball) two areas stay apart. The
    corners and narrow strips a large ball misses are filled by the smaller ones (Zhang et al. 2009)."""
    reg = np.zeros(free.shape, np.int32)
    n = 0
    for r in radii:
        todo = free & (reg == 0)
        k, cc = cv2.connectedComponents(cv2.erode(todo.astype(np.uint8), disk(r)), connectivity=8)
        if k <= 1:
            continue
        dist, near = nearest(cc)
        grow = todo & (near > 0) & (dist <= r + 0.5)
        reg[grow] = near[grow] + n
        n += k - 1
    return reg


def regions_of(img, within, L, s, upscaled=1):
    """The regions: the areas the source's lines enclose, the line pixels and the slivers going to the nearest one,
    then the tiny ones (a catch-light, a speck) joined to the touching region nearest in colour. Returns the region
    map, the line pixels and the core pixels (inside the lines, off the figure's edge) the colours are read from."""
    line = (find_lines(img, upscaled) > 0.3) & within
    free = within & ~line
    reg = trapped_ball(free, sorted({max(1, int(round(r * s))) for r in (8, 5, 3, 2)}, reverse=True))
    _, near = nearest(reg)
    reg = relabel(np.where(within, np.where(reg > 0, reg, near), 0).astype(np.int32))
    core = free & (cv2.erode(within.astype(np.uint8), disk(1)) > 0)
    for _ in range(3):
        st = region_stats(reg, L, core)
        nb = neighbours(adjacency(reg))
        tiny = np.flatnonzero((st["area"] < 60 * s * s) & (np.arange(len(st["area"])) > 0))
        if not len(tiny):
            break
        lut = np.arange(len(st["area"]), dtype=np.int32)
        for i in tiny:
            cand = [(cdist(st["lab"][i], st["lab"][j]), -c, j) for j, c in nb.get(int(i), {}).items()
                    if j != 0 and st["area"][j] >= st["area"][i]]
            if cand:
                lut[i] = min(cand)[2]
        for _k in range(4):
            lut = lut[lut]
        reg = relabel(lut[reg])
    return reg, line, core


def relabel(reg, with_lut=False):
    """Region numbers made consecutive from 1, in reading order of each region's first pixel."""
    keys, first = np.unique(reg.ravel(), return_index=True)
    keys = keys[np.argsort(first)]
    lut = np.zeros(int(keys.max()) + 1, np.int32)
    lut[keys[keys > 0]] = np.arange(1, int((keys > 0).sum()) + 1)
    return (lut[reg], lut) if with_lut else lut[reg]


def adjacency(reg):
    """The boundary length between every pair of touching regions (0 is outside the figure): {(i, j): pixels}, i < j."""
    a = np.concatenate([reg[:, :-1].ravel(), reg[:-1, :].ravel()])
    b = np.concatenate([reg[:, 1:].ravel(), reg[1:, :].ravel()])
    m = a != b
    lo, hi = np.minimum(a[m], b[m]).astype(np.int64), np.maximum(a[m], b[m]).astype(np.int64)
    keys, counts = np.unique(lo * (int(reg.max()) + 1) + hi, return_counts=True)
    n1 = int(reg.max()) + 1
    return {(int(k // n1), int(k % n1)): int(c) for k, c in zip(keys, counts)}


def neighbours(adj):
    out = {}
    for (i, j), c in adj.items():
        out.setdefault(i, {})[j] = c
        out.setdefault(j, {})[i] = c
    return out


def region_stats(reg, L, core):
    """Per region: area, centroid, box, the median Lab of its core (inside its lines, off its edge) and the 10th, 50th
    and 90th percentile of its lightness. A region with no core uses all its pixels."""
    n = int(reg.max())
    flat = reg.ravel()
    area = np.bincount(flat, minlength=n + 1)
    ys, xs = np.indices(reg.shape)
    cy = np.bincount(flat, weights=ys.ravel(), minlength=n + 1) / np.maximum(area, 1)
    cx = np.bincount(flat, weights=xs.ravel(), minlength=n + 1) / np.maximum(area, 1)
    sl = ndi.find_objects(reg)
    use = core.ravel() & (flat > 0)
    have = np.bincount(flat[use], minlength=n + 1)
    use = use | ((have[flat] == 0) & (flat > 0))
    lab_ = flat[use]
    stats = {"area": area, "cy": cy, "cx": cx, "box": sl}
    for c, key in ((0, "L"), (1, "a"), (2, "b")):
        v = L[..., c].ravel()[use]
        order = np.lexsort((v, lab_))
        sv, sl_ = v[order], lab_[order]
        start = np.searchsorted(sl_, np.arange(n + 1))
        cnt = np.bincount(sl_, minlength=n + 1)
        qs = (0.5,) if c else (0.1, 0.5, 0.9)
        for q in qs:
            idx = np.clip(start + (q * np.maximum(cnt - 1, 0)).astype(np.int64), 0, max(0, len(sv) - 1))
            val = np.where(cnt > 0, sv[idx] if len(sv) else 0, 0)
            stats[f"{key}{int(q * 100)}"] = val
    stats["lab"] = np.stack([stats["L50"], stats["a50"], stats["b50"]], -1)
    return stats


# ------------------------------------------------------------------------------------------------------------ colour

def chroma(c):
    return math.hypot(float(c[1]), float(c[2]))


def hue(c):
    return math.degrees(math.atan2(float(c[2]), float(c[1]))) % 360


def cdist(c1, c2, wl=None):
    """Colour distance for telling materials apart: for a colourful pair lightness counts for less (a part's lit and
    shaded tones differ mostly in lightness), for greys it is all there is."""
    if wl is None:
        cmin = min(chroma(c1), chroma(c2))
        wl = 1.0 if cmin < 6 else 0.4 if cmin > 14 else 1.0 - 0.6 * (cmin - 6) / 8
    dl, da, db = (float(c1[0]) - float(c2[0])), float(c1[1]) - float(c2[1]), float(c1[2]) - float(c2[2])
    return math.sqrt(da * da + db * db + (wl * dl) ** 2)


def skin_like(c):
    L, C, h = float(c[0]), chroma(c), hue(c)
    return 30 <= L <= 97 and 3.5 <= C <= 40 and (12 <= h <= 88) and float(c[1]) > 0


def colour_word(c):
    L, C = float(c[0]), chroma(c)
    if C < 7:
        return "white" if L > 84 else "grey" if L > 32 else "black"
    h = hue(c)
    if h >= 345 or h < 25:
        return "pink" if L > 62 else "crimson"
    if h < 50:
        return "salmon" if L > 70 else "red"
    if h < 80:
        return "brown" if L < 55 else "orange" if C > 42 else "beige"
    if h < 115:
        return "yellow" if L > 60 else "olive"
    if h < 170:
        return "green"
    if h < 230:
        return "teal"
    if h < 315:
        return "navy" if L < 35 else "blue"
    return "purple" if L < 65 else "lilac"


# -------------------------------------------------------------------------------------------------------------- face

def skin_of(L, c, wl=0.6, t=13.0):
    """The pixels of one skin colour: its shaded tones (darker, lightness counting for less) and its lit ones (lighter
    and paler, along the way from the colour toward white), but not a white or a grey near a pale skin (too little
    colour, or colour of another hue)."""
    Lc, ac, bc = (float(v) for v in c)
    up = np.clip((L[..., 0] - Lc) / max(1.0, 100.0 - Lc), 0, 0.75)
    dl = np.maximum(0.0, Lc - L[..., 0]) * wl
    m = np.sqrt(dl ** 2 + (L[..., 1] - ac * (1 - up)) ** 2 + (L[..., 2] - bc * (1 - up)) ** 2) < t
    cs = chroma(c)
    if cs >= 6:
        C = np.hypot(L[..., 1], L[..., 2])
        dh = np.abs((np.degrees(np.arctan2(L[..., 2], L[..., 1])) - hue(c) + 180) % 360 - 180)
        m &= (C >= max(2.5, 0.2 * cs)) & ((dh < 40) | (C < 3))
    return m


def hull_of(m):
    out = np.zeros(m.shape, np.uint8)
    pts = cv2.findNonZero(m.astype(np.uint8))
    if pts is not None:
        cv2.fillConvexPoly(out, cv2.convexHull(pts), 1)
    return out > 0


def catchlight(blob, Lc, skin_L=90.0):
    """Whether a hole holds a catch-light: a small bright spot ringed all round by the darker colour of an iris (a
    lock of hair has none; a shine on hair is a long streak, not a spot). Bright and dark are read against the skin,
    so a picture graded to night, its catch-lights dimmed, is read alike."""
    bright = ((Lc > min(85.0, skin_L + 4)) & (cv2.dilate(blob.astype(np.uint8), disk(2)) > 0)).astype(np.uint8)
    k, cc, st, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
    size = blob.sum()
    for i in range(1, k):
        x, y, w, h, a = (int(v) for v in st[i])
        if not (3 <= a <= 0.12 * size) or max(w, h) > 3 * min(w, h) + 2:
            continue
        spot = (cc == i).astype(np.uint8)
        ring = (cv2.dilate(spot, disk(2)) > 0) & (spot == 0)
        if ring.sum() and blob[ring].mean() > 0.6 and np.median(Lc[ring]) < min(62.0, skin_L - 12):
            return True
    return False


def eye_candidates(holes, face, L, X, top, skin_L, r):
    """The holes shaped and filled like an eye, each scored: size, fill, dark marks, light marks, a catch-light. A
    hole too tall for an eye may be an eye with a lock of the bangs over it (the lock running into it, the same
    colour as the iris): its lowest part, an eye's height, is tried instead. An eye sits in the face: a good share
    of what rings it is the face's skin (a lock clasp in the hair above the face, with its shine, is not an eye)."""
    k, cc, cst, cen = cv2.connectedComponentsWithStats(
        cv2.morphologyEx(holes.astype(np.uint8), cv2.MORPH_OPEN, disk(r)), connectivity=8)
    out = []
    for c in range(1, k):
        bx, by, bw, bh, a = (int(v) for v in cst[c])
        if not (0.07 * X <= bw <= 0.6 * X and 0.04 * X <= bh):
            continue
        blob = cc[by:by + bh, bx:bx + bw] == c
        if bh > 0.45 * X:
            cut = bh - int(0.35 * X)
            blob[:cut] = False
            ys_, xs_ = np.nonzero(blob)
            if len(ys_) < 0.002 * X * X:
                continue
            by, bx = by + int(ys_.min()), bx + int(xs_.min())
            blob = blob[ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1]
            bh, bw = blob.shape
            a = int(blob.sum())
            cen[c] = (bx + float(xs_.mean() - xs_.min()), by + float(ys_.mean() - ys_.min()))
            if bw < 0.07 * X:
                continue
        if not (0.45 <= bw / bh <= 4.5):
            continue
        fill, cy = a / float(bw * bh), float(cen[c][1])
        if fill < 0.3 or not (top - 0.25 * X <= cy <= top + 1.05 * X):
            continue
        # read with its inner specks filled: a catch-light tinted like the skin is no hole of its own
        full = ndi.binary_fill_holes(blob)
        Lp = L[by:by + bh, bx:bx + bw, 0][full]
        dark, light = float((Lp < 45).mean()), float((Lp > min(78.0, skin_L + 6)).mean())
        if dark < 0.04:
            continue
        y0, y1, x0, x1 = max(0, by - 2 * r), by + bh + 2 * r, max(0, bx - 2 * r), bx + bw + 2 * r
        own = np.zeros(holes[y0:y1, x0:x1].shape, np.uint8)
        own[by - y0:by - y0 + bh, bx - x0:bx - x0 + bw] = blob
        ring = (cv2.dilate(own, disk(max(2, 0.03 * X))) > 0) & (own == 0)
        on_face = float(face[y0:y1, x0:x1][ring].mean()) if ring.any() else 0.0
        if on_face < 0.25:
            continue
        score = (math.sqrt(a) * fill * min(1.0, dark / 0.15) * (0.4 + 0.6 * min(1.0, light / 0.06))
                 * min(1.0, on_face / 0.5))
        shine = catchlight(full, L[by:by + bh, bx:bx + bw, 0], skin_L)
        if shine:
            score *= 2.5
        # the hole as found, with what the opening shaved off near it (the thin ends of the lashes)
        mask = np.zeros(holes.shape, bool)
        mask[y0:y1, x0:x1] = holes[y0:y1, x0:x1] & (cv2.dilate(own, disk(2 * r)) > 0)
        # its look, to match it with the other eye: the colour of its middle tones (the iris, not the lashes or the
        # white or the shine)
        px = L[by:by + bh, bx:bx + bw][full]
        mid = px[(px[:, 0] > 18) & (px[:, 0] < 88)]
        out.append({"box": [bx, by, bx + bw, by + bh], "centre": [float(cen[c][0]), cy], "area": a,
                    "score": score, "mask": mask, "look": np.median(mid if len(mid) > 20 else px, axis=0),
                    "shine": shine})
    return out


def overlap(b1, b2):
    """The share of the smaller box that the two boxes have in common."""
    w = min(b1[2], b2[2]) - max(b1[0], b2[0])
    h = min(b1[3], b2[3]) - max(b1[1], b2[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / float(min((b1[2] - b1[0]) * (b1[3] - b1[1]), (b2[2] - b2[0]) * (b2[3] - b2[1])))


def face_width(F):
    """The top of a face's skin and its width: the widest rows of its upper part (the cheeks; a neck or shoulders of
    the same skin below do not count)."""
    ys, xs = np.nonzero(F)
    top, height = int(ys.min()), int(ys.max() - ys.min() + 1)
    rows = ys < top + 0.6 * height
    lo = np.full(height, np.inf)
    hi = np.full(height, -np.inf)
    np.minimum.at(lo, ys[rows] - top, xs[rows])
    np.maximum.at(hi, ys[rows] - top, xs[rows])
    return top, float(np.percentile((hi - lo)[np.isfinite(lo)], 90)) + 1


def eyes_in(F, skin, L, within, reg, line, skin_L=90.0, hints=None):
    """The eyes of a face: the compact holes its skin leaves inside its outline (an iris with its lashes, the white
    where it is greyer than the skin), a pair side by side (the head tilted up to 45 degrees), else the
    clearest one; a hole with a catch-light counts for more. The outline is raised a little, for bangs that hide the
    skin above an eye. What reaches into it from outside (a lock of the bangs over an eye) is no hole, so the holes
    are read several ways (as they are; with the regions lying mostly outside the outline taken out, which also takes
    out an iris whose region ran into hair of its colour; with openings that cut thin joins; without the line art,
    for a glasses frame round the eyes), and the best eyes of any reading win. An eye holds some of
    the darkest marks (lashes, pupil) and mostly some light ones that are not skin (the white, a catch-light: lighter
    than the skin, so a picture graded to night is read alike; an eye drawn in heavy ink may have none). The two eyes
    of a pair look alike (the colour of the irises, the size): a pair of unlike holes counts for less. F is the face's
    skin, skin every pixel of its colour. With hints (rough boxes round the eyes, given by whoever looked at the
    picture) each eye is the best hole in its box, or the box's holes when none reads as an eye. Returns the eyes
    ({box, centre, area, score, mask, look}), how sure the reading is, the head (the skin above the chin) and the
    face's width."""
    top, X = face_width(F)
    head = F & (np.arange(F.shape[0])[:, None] < top + 1.4 * X)
    # the outline, raised for bangs over the skin above an eye and widened for an eye at the edge of a face seen
    # from the side; the skin closed over small specks (blush hatching, grain) that are no eye
    area = hull_of(head)
    d = int(0.3 * X)
    area[:-d] |= area[d:].copy()
    area = cv2.dilate(area.astype(np.uint8), np.ones((1, 2 * int(0.06 * X) + 1), np.uint8)) > 0
    skin = cv2.morphologyEx(skin.astype(np.uint8), cv2.MORPH_CLOSE, disk(max(1, 0.008 * X))) > 0
    n = int(reg.max()) + 1
    inside = np.bincount(reg[area], minlength=n) / np.maximum(np.bincount(reg.ravel(), minlength=n), 1)
    holes = area & ~skin & within
    r = max(1, int(round(0.012 * X)))
    cands = []
    found = []
    # the larger openings cut what joins an eye to something else: the thin locks of the bangs, a glasses frame
    for rr in (r, 2 * r, 3 * r):
        found += eye_candidates(holes & (inside[reg] >= 0.6), head, L, X, top, skin_L, rr)
        found += eye_candidates(holes, head, L, X, top, skin_L, rr)
    # and without the line art: a glasses frame is a line, an eye's iris and white are not
    found += eye_candidates(holes & ~line, head, L, X, top, skin_L, r)
    for c in found:
        same = [q for q in cands if overlap(q["box"], c["box"]) > 0.7]
        if not same:
            cands.append(c)
        elif c["score"] > same[0]["score"]:
            cands[cands.index(same[0])] = c
    if hints:
        if not all(area[min(area.shape[0] - 1, max(0, (b[1] + b[3]) // 2)), min(area.shape[1] - 1, max(0, (b[0] + b[2]) // 2))]
                   for b in hints):
            return [], 0.0, head, X                 # not the face the boxes are on
        eyes = []
        for b in hints:
            mine = [c for c in cands if overlap(c["box"], b) > 0.3]
            if mine:
                # the hole found, within the box given: the box the reviewer drew holds the whole eye (a hole may be
                # only its upper half, the lower lid's line cutting it off), so the eye's box is the two together
                e = dict(max(mine, key=lambda e: e["score"]))
                e["box"] = [min(e["box"][0], b[0]), min(e["box"][1], b[1]), max(e["box"][2], b[2]),
                            max(e["box"][3], b[3])]
                eyes.append(e)
                continue
            m = np.zeros(holes.shape, bool)
            m[max(0, b[1]):b[3], max(0, b[0]):b[2]] = True
            m &= holes
            px = L[m] if m.any() else L[max(0, b[1]):b[3], max(0, b[0]):b[2]].reshape(-1, 3)
            eyes.append({"box": list(b), "centre": [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0], "area": int(m.sum()),
                         "score": 1.0, "mask": m, "look": np.median(px, axis=0), "shine": False})
        # every area whose outline holds the boxes passes: brown or blonde hair round the face, of a skin-like hue,
        # holds them as well as the skin does. The face is the one whose own pixels are the cheeks under the boxes
        cheek = []
        for b in hints:
            hb = max(4, int(0.8 * (b[3] - b[1])))
            band = F[max(0, b[3]):max(0, b[3] + hb), max(0, b[0]):max(0, b[2])]
            cheek.append(float(band.mean()) if band.size else 0.0)
        return sorted(eyes, key=lambda e: e["centre"][0]), 1e6 * (0.05 + min(cheek)), head, X
    eyes = sorted(cands, key=lambda e: -e["score"])[:1]
    best = 0.45 * eyes[0]["score"] if eyes else 0.0
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            ea, eb = cands[i], cands[j]
            dy, dx = abs(ea["centre"][1] - eb["centre"][1]), abs(ea["centre"][0] - eb["centre"][0])
            size = min(ea["area"], eb["area"]) / max(ea["area"], eb["area"])
            if dy < dx and 0.15 * X < dx < 0.8 * X and size > 0.2 and overlap(ea["box"], eb["box"]) < 0.1:
                alike = math.exp(-float(np.linalg.norm(ea["look"] - eb["look"])) / 40.0) * (0.5 + 0.5 * size)
                sc = (ea["score"] + eb["score"]) * alike
                if sc > best:
                    best, eyes = sc, [ea, eb]
    return sorted(eyes, key=lambda e: e["centre"][0]), best, head, X


def mouth_in(head, eyes, L, skin_c, X, hint=None):
    """The mouth: below the eyes and between them (or in the rough box given), the widest mark that is not skin (the
    line of a closed mouth, the inside of an open one), away from the outline of the jaw. Returns (box, mask) or
    None."""
    h, w = head.shape
    zone = np.zeros((h, w), bool)
    if hint is not None:
        x0, y0, x1, y1 = hint
        dx, dy = int(0.15 * (x1 - x0)), int(0.15 * (y1 - y0))
        zone[max(0, y0 - dy):y1 + dy, max(0, x0 - dx):x1 + dx] = True
        span = 2.0 * (x1 - x0)
    else:
        ex = sum(e["centre"][0] for e in eyes) / len(eyes)
        eb = max(e["box"][3] for e in eyes)
        span = abs(eyes[1]["centre"][0] - eyes[0]["centre"][0]) if len(eyes) == 2 else 0.45 * X
        zone[int(eb + 0.2 * span):max(0, int(eb + 1.5 * span)), max(0, int(ex - 0.75 * span)):int(ex + 0.75 * span)] = True
    inner = cv2.erode(hull_of(head).astype(np.uint8), disk(max(1, 0.04 * X))) > 0
    if hint is not None:
        inner = np.ones_like(inner)
    darker = L[..., 0] < skin_c[0] - 22
    marks = zone & inner & (~head | darker)
    kx = max(3, int(0.05 * span)) | 1
    marks = cv2.morphologyEx(marks.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, kx), np.uint8))
    k, cc, cst, _ = cv2.connectedComponentsWithStats(marks, connectivity=8)
    if k <= 1:
        return None
    c = 1 + int(np.argmax(cst[1:, cv2.CC_STAT_WIDTH]))
    bx, by, bw, bh, _ = (int(v) for v in cst[c])
    if hint is not None:
        # the box given and the mark found together, the mark held near the box: the half of a smile the mark
        # missed is in the box, and a beard or a collar the mark ran into is not the mouth
        x0, y0, x1, y1 = hint
        dx, dy = 0.2 * (x1 - x0), 0.2 * (y1 - y0)
        box = [int(max(min(x0, bx), x0 - dx)), int(max(min(y0, by), y0 - dy)),
               int(min(max(x1, bx + bw), x1 + dx)), int(min(max(y1, by + bh), y1 + dy))]
        lim = np.zeros((h, w), bool)
        lim[max(0, box[1]):box[3], max(0, box[0]):box[2]] = True
        return box, (cc == c) & lim
    if bw < 0.12 * span:
        return None
    return [bx, by, bx + bw, by + bh], (cc == c)


def find_face(L, within, reg, line, fig, s, hints=None):
    """The face: in the top half of the figure, the skin-coloured area that holds a pair of eyes. The skin's colour
    is not known beforehand (a blonde, a ginger or a brown head of hair is skin-coloured too, and so are a beige
    coat and gold armour): each likely colour is tried, and the area holding the best pair of eyes wins. The skin's
    colour is then read again from the cheeks under the eyes, and the face is the area of that colour round them.
    hints: {"eyes": [box, ...], "mouth": box}, rough boxes in the picture's pixels, given by whoever looked at it."""
    hints = hints or {}
    hgt = fig["height"]
    y0 = int(fig["y_top"])
    y1 = min(within.shape[0], int(fig["y_top"] + 0.55 * hgt))
    Lh, wh, rh, lh = L[y0:y1], within[y0:y1], reg[y0:y1], line[y0:y1]
    eye_hints = [[int(b[0]), int(b[1]) - y0, int(b[2]), int(b[3]) - y0] for b in hints.get("eyes", [])] or None
    mouth_hint = hints.get("mouth")
    if mouth_hint is not None:
        mouth_hint = [int(mouth_hint[0]), int(mouth_hint[1]) - y0, int(mouth_hint[2]), int(mouth_hint[3]) - y0]
    C = np.hypot(Lh[..., 1], Lh[..., 2])
    hh = np.degrees(np.arctan2(Lh[..., 2], Lh[..., 1])) % 360
    px = Lh[wh & (Lh[..., 0] > 25) & (C > 3.5) & (C < 42) & (hh > 25) & (hh < 76) & (Lh[..., 1] > 3)]
    if len(px) < 500:
        return None
    sub = px[np.random.default_rng(0).choice(len(px), min(len(px), 30000), replace=False)].astype(np.float32)
    wv = np.array([0.6, 1, 1], np.float32)
    _, _, cen = cv2.kmeans(sub * wv, 5, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3,
                           cv2.KMEANS_PP_CENTERS)
    best, lightest = None, None
    for c in [np.median(px, axis=0)] + [q / wv for q in cen]:
        if c[1] < 3 or not 25 < hue(c) < 76:
            continue
        sk = skin_of(Lh, c) & wh
        m = cv2.morphologyEx(sk.astype(np.uint8), cv2.MORPH_OPEN, disk(max(1, 1.5 * s)))
        k, cc, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for comp in np.argsort(-st[1:, cv2.CC_STAT_AREA])[:4] + 1:
            if st[comp, cv2.CC_STAT_AREA] < 0.002 * fig["area"]:
                break
            high = st[comp, cv2.CC_STAT_TOP] + st[comp, cv2.CC_STAT_HEIGHT] / 2 < 0.45 * hgt
            if high and (lightest is None or c[0] > lightest[0][0]):
                lightest = (c, cc == comp)
            eyes, sure, head, X = eyes_in(cc == comp, sk, Lh, wh, rh, lh, float(c[0]), eye_hints)
            if not eyes:
                continue
            rel = np.nonzero(head.any(axis=1))[0].mean() / hgt
            # the head is near the top of a figure: a pair of "eyes" in a belt or a pocket lower down counts for little
            score = sure * math.exp(-max(0.0, rel - 0.15) / 0.12)
            if best is None or score > best["score"]:
                best = {"score": score, "colour": c, "eyes": eyes, "head": head, "X": X}
    # a pair is believed when it is strong, or when it is fair and an eye shows a catch-light or both are of a good size
    # for the face (a pair of specks on a glasses frame is neither)
    sure = best is not None and (best["score"] >= 0.08 * best["X"] or (best["score"] >= 0.01 * best["X"] and (
        any(e["shine"] for e in best["eyes"]) or
        (len(best["eyes"]) == 2 and min(e["area"] for e in best["eyes"]) >= 0.012 * best["X"] ** 2))))
    if not sure:
        # no clear pair of eyes (glasses, closed eyes, a face turned away): the face is the lightest skin-coloured
        # area high in the figure (hair of a skin-like hue is darker than the skin, or too colourful to be skin), and
        # the eyes and the mouth are left to the reviewer
        if lightest is None:
            return None
        top, X = face_width(lightest[1])
        best = {"colour": lightest[0], "eyes": [], "X": X,
                "head": lightest[1] & (np.arange(lightest[1].shape[0])[:, None] < top + 1.4 * X)}
    if eye_hints and not best["eyes"]:
        # the face found but no eyes read in it (glasses over them, eyes closed): the boxes given are the eyes, what
        # in them is not skin their mask (a glasses frame inside a box is kept with the eye, as drawn)
        sk_h = skin_of(Lh, best["colour"]) & wh
        given = []
        for b in eye_hints:
            m = np.zeros(wh.shape, bool)
            m[max(0, b[1]):max(0, b[3]), max(0, b[0]):max(0, b[2])] = True
            px = Lh[m & wh] if (m & wh).any() else Lh[m]
            m &= ~sk_h & wh
            given.append({"box": list(b), "centre": [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0], "area": int(m.sum()),
                          "score": 1.0, "mask": m, "look": np.median(px.reshape(-1, 3), axis=0), "shine": False,
                          "given": True})
        best["eyes"] = sorted(given, key=lambda e: e["centre"][0])
    # the cheeks: under each eye, as wide as the eye, down by about its height; their median is the skin's colour
    cheek = np.zeros(wh.shape, bool)
    for e in best["eyes"]:
        x0, ey0, x1, ey1 = e["box"]
        eh = ey1 - ey0
        cheek[int(ey1 + 0.3 * eh):int(ey1 + 1.3 * eh), x0:x1] = True
    near = cheek & skin_of(Lh, best["colour"], t=18.0) & wh
    skin_c = np.median(Lh[near], axis=0) if near.sum() > 30 else best["colour"]
    if not best["eyes"]:
        near = best["head"]
    sk = skin_of(Lh, skin_c) & wh
    m = cv2.morphologyEx(sk.astype(np.uint8), cv2.MORPH_OPEN, disk(max(1, 1.5 * s)))
    k, cc, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    ids, cnt = np.unique(cc[near & (cc > 0)], return_counts=True)
    if len(ids):
        F = cc == ids[np.argmax(cnt)]
        ys = np.nonzero(F)[0]
        head = F & (np.arange(F.shape[0])[:, None] < ys.min() + 1.4 * best["X"])
    else:
        head = best["head"]
    mb = mouth_in(head, best["eyes"], Lh, skin_c, best["X"], mouth_hint) if best["eyes"] or mouth_hint else None
    if mb is None and mouth_hint is not None:
        x0, my0, x1, my1 = mouth_hint
        mm = np.zeros(wh.shape, bool)
        mm[max(0, my0):my1, max(0, x0):x1] = True
        mb = (mouth_hint, mm & ~sk & wh)

    def full(m_):
        out = np.zeros(within.shape, bool)
        out[y0:y1] = m_
        return out

    for e in best["eyes"]:
        e["box"] = [e["box"][0], e["box"][1] + y0, e["box"][2], e["box"][3] + y0]
        e["centre"] = [e["centre"][0], e["centre"][1] + y0]
        e["mask"] = full(e["mask"])
    head = full(head)
    ys, xs = np.nonzero(head)
    return {"colour": skin_c, "eyes": best["eyes"], "head": head, "X": best["X"],
            "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
            "mouth": None if mb is None else ([mb[0][0], mb[0][1] + y0, mb[0][2], mb[0][3] + y0], full(mb[1]))}


def pad_box(b, frac, px, h, w):
    x0, y0, x1, y1 = b
    dx, dy = max(px, frac * (x1 - x0)), max(px, frac * (y1 - y0))
    return [int(max(0, x0 - dx)), int(max(0, y0 - dy)), int(min(w, x1 + dx)), int(min(h, y1 + dy))]


# ------------------------------------------------------------------------------------------------------------- parts

def is_skin(c, skin_c, t=12.0):
    """Whether a region's colour is the skin's: near it (lightness counting for less, and less still on the shaded
    side), with about its colourfulness and its hue. A white shirt or a cream tee beside a pale skin is near in colour
    but greyer, or of another hue."""
    if cdist(c, skin_c, 0.4 if c[0] < skin_c[0] else 0.6) > t:
        return False
    cs = chroma(skin_c)
    if cs < 6:
        return True
    dh = abs((hue(c) - hue(skin_c) + 180) % 360 - 180)
    return chroma(c) >= 0.55 * cs and dh <= 18


def contact(reg, j, group_mask, box):
    """Where region j meets a group of regions: the width of the meeting (pixels across) and its height in j (0 at
    j's top, 1 at its bottom)."""
    y0, y1, x0, x1 = box[0].start, box[0].stop, box[1].start, box[1].stop
    m = reg[y0:y1, x0:x1] == j
    near = cv2.dilate(group_mask[y0:y1, x0:x1].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    ys, xs = np.nonzero(m & near)
    if not len(ys):
        return 0, 1.0
    return int(xs.max() - xs.min() + 1), float((ys.mean() - 0) / max(1, y1 - y0))


def hair_above(reg, j, hair, box, reach):
    """The share of region j's columns that have hair within `reach` pixels straight above the region's top edge."""
    y0, y1, x0, x1 = box[0].start, box[0].stop, box[1].start, box[1].stop
    m = reg[y0:y1, x0:x1] == j
    cols = np.flatnonzero(m.any(axis=0))
    if not len(cols):
        return 0.0
    tops = y0 + m[:, cols].argmax(axis=0)
    hit = 0
    for c, t in zip(cols, tops):
        hit += bool(hair[max(0, t - reach):t, x0 + c].any())
    return hit / float(len(cols))


def grow_hair(reg, face_regs, eye_y, X, skin_c, st, nb, fig, taken):
    """The hair: the regions round the face above its eyes that are not skin (the bangs, the side locks), then every
    region of their colour that touches the hair along a good part of its edge, or that carries on from the hair
    below it across most of its width (a lock hanging on below the shoulder; not a skirt of the same colour that only
    meets the hair's tips at one side), the shines inside the hair (whatever their colour, when the hair rings
    them), and the hair a shoulder hides for a stretch (the long hair below it)."""
    seeds = {}
    for f in face_regs:
        for j, c in nb.get(f, {}).items():
            if j == 0 or taken[j] or j in face_regs:
                continue
            if st["cy"][j] < eye_y + 0.1 * X and not is_skin(st["lab"][j], skin_c):
                seeds[j] = seeds.get(j, 0) + c
    seeds = {j: c for j, c in seeds.items() if c >= 6}
    if not seeds:
        return set(), None
    # the hair's colour: of the seeds' colours, the one most of their area shares (an eyebrow or a shadow on the
    # forehead touches the face along as much of its edge as the hair does, but is far smaller)
    def group_area(j):
        return sum(st["area"][k] for k in seeds if cdist(st["lab"][k], st["lab"][j]) <= 14)
    main = max(seeds, key=group_area)
    group = [k for k in seeds if cdist(st["lab"][k], st["lab"][main]) <= 14]
    weights = np.array([st["area"][k] for k in group], np.float64)
    hair_c = (st["lab"][group] * weights[:, None]).sum(0) / weights.sum()
    hair = {j for j in seeds if cdist(st["lab"][j], hair_c) <= 16}
    lut = np.zeros(len(st["area"]), bool)
    lut[list(hair)] = True
    frontier = list(hair)
    while True:
        while frontier:
            nxt = []
            for i in frontier:
                for j in nb.get(i, {}):
                    if j == 0 or j in hair or taken[j] or j in face_regs:
                        continue
                    cj = st["lab"][j]
                    edge = sum(c for k, c in nb[j].items() if k != 0)
                    shared = sum(c for k, c in nb[j].items() if k in hair)
                    ringed = shared >= 0.8 * max(edge, 1) and st["area"][j] < 0.01 * fig["area"]
                    if not ringed and (cdist(cj, hair_c) > 14 or is_skin(cj, skin_c)):
                        continue
                    if not ringed and shared < 0.2 * max(edge, 1) and st["area"][j] > 0.002 * fig["area"]:
                        sl = st["box"][j - 1]
                        width, where = contact(reg, j, lut[reg], sl)
                        if not (where < 0.3 and width >= 0.5 * (sl[1].stop - sl[1].start)):
                            continue
                    hair.add(j)
                    lut[j] = True
                    if not ringed or cdist(cj, hair_c) <= 14:      # a shine joins the hair but does not grow it
                        nxt.append(j)
            frontier = nxt
        # hair that a shoulder or an arm hides for a stretch: a region of the hair's colour, not touching it, whose
        # top edge has hair a short way straight above it along most of its width
        mask = lut[reg]
        for j in range(1, len(st["area"])):
            if j in hair or taken[j] or j in face_regs or st["area"][j] < 0.0001 * fig["area"]:
                continue
            if cdist(st["lab"][j], hair_c) > 10 or is_skin(st["lab"][j], skin_c):
                continue
            if hair_above(reg, j, mask, st["box"][j - 1], int(X)) >= 0.4:
                hair.add(j)
                lut[j] = True
                frontier.append(j)
        if not frontier:
            return hair, hair_c


def tolerant(px, c):
    """Distance from a colour with lightness counting for less (a part's shading), fully for greys and whites (where
    lightness is all there is)."""
    wl = 1.0 if chroma(c) < 6 else 0.4
    return np.sqrt((wl * (px[..., 0] - c[0])) ** 2 + (px[..., 1] - c[1]) ** 2 + (px[..., 2] - c[2]) ** 2)


def split_by_hints(reg, hint_parts, L, s, far=22.0, inner_margin=8.0, line=None):
    """A region that holds points of two or more parts (the line finder missed the outline between them: a print on
    a shirt, a hair clip, a coat and trousers of one navy in a painting with few lines) is split among them by a
    watershed from markers (Beucher and Meyer 1993; computed as an image foresting transform, Falcao et al. 2004):
    each part's points flood the region at once, a pixel at a time in the order of the colour step to it, so where two
    parts meet, the boundary falls on the strongest colour edge between them, however soft the shading on either side.
    What is far in colour from every point of the part that flooded it (a material nobody pointed at) is set apart as a
    region of its own for the parts' growth to settle; so is what is far from the points of the only part pointed at
    in a region (a white collar flap in one region with the navy stripe pointed at on it). Returns the region map and
    the regions it made (bounded by the watershed and the colour test, not by drawn lines)."""
    pts = {}
    for k, hp in enumerate(hint_parts):
        for x, y in hp.get("at", []):
            x, y = int(x), int(y)
            if 0 <= y < reg.shape[0] and 0 <= x < reg.shape[1] and reg[y, x] > 0:
                c = np.median(L[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3), axis=0)
                pts.setdefault(int(reg[y, x]), []).append((k, (x, y), c))
    boxes = ndi.find_objects(reg)
    nid = int(reg.max())
    r = max(1, int(round(2 * s)))
    min_area = max(40.0, 60.0 * s * s)
    made = set()
    for j, found in pts.items():
        ks = sorted({k for k, _, _ in found})
        sl = boxes[j - 1]
        m = reg[sl] == j
        on = (line[sl] & m) if line is not None else np.zeros(m.shape, bool)
        if len(ks) >= 2:
            Lc = cv2.GaussianBlur(L[sl], (0, 0), 1.0)
            g = np.sqrt(sum(cv2.Sobel(Lc[..., c], cv2.CV_32F, 1, 0) ** 2 + cv2.Sobel(Lc[..., c], cv2.CV_32F, 0, 1) ** 2
                            for c in range(3))) / 4.0
            # an edge with one part's colours on both sides (its lit and its shaded tone, each nearest that part's
            # points by a clear margin) is that part's shading, not a border, and is damped: where a faint line
            # between two dark materials is no stronger than one material's own shading step, the boundary still
            # falls on the line. Parts of one colour (a navy coat on navy trousers) have no clear margin: their
            # edges are left as they are
            near = np.stack([np.min(np.stack([tolerant(Lc, c) for kk, _, c in found if kk == k]), axis=0) for k in ks])
            srt = np.sort(near, axis=0)
            best = np.argmin(near, axis=0)
            sure = srt[1] - srt[0] >= inner_margin
            inner = np.zeros(m.shape, bool)
            for q in range(len(ks)):
                inner |= cv2.erode(((best == q) & sure).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            g = np.where(inner, g * 0.25, g)
            g8 = np.where(m, np.clip(g * 4.0, 0, 254), 255).astype(np.uint8)
            markers = np.zeros(m.shape, np.int32)
            for k, (x, y), _ in found:
                disc = np.zeros(m.shape, np.uint8)
                cv2.circle(disc, (x - sl[1].start, y - sl[0].start), r, 1, -1)
                markers[(disc > 0) & m] = ks.index(k) + 1
            lab_ = ndi.watershed_ift(g8, markers)
            if on.any() and (m & ~on).any():
                # the line art is one dark network running between every material, its inside without edges: a dark
                # part's flood runs along it round its neighbours. A line goes with the fill nearest it instead
                _, nl = nearest(np.where(m & ~on, lab_, 0).astype(np.int32))
                lab_ = np.where(on, nl, lab_)
        else:
            lab_ = m.astype(np.int32)                  # one part's points: the region is its, but for what is far
        block = reg[sl]
        for q, k in enumerate(ks, start=1):
            mine = (lab_ == q) & m
            if not mine.any():
                continue
            cols = [c for kk, _, c in found if kk == k]
            d = np.min(np.stack([tolerant(L[sl][mine], c) for c in cols]), axis=0)
            away = np.zeros(m.shape, bool)
            away[mine] = d > far
            away &= ~on                                # (a line is far from every fill's colour)
            n_, cc = cv2.connectedComponents(away.astype(np.uint8), connectivity=8)
            for i in range(1, n_):
                piece = cc == i
                if piece.sum() >= min_area:
                    nid += 1
                    block[piece] = nid
                    made.add(nid)
                    mine &= ~piece
            nid += 1
            block[mine] = nid
            if len(ks) >= 2:
                made.add(nid)
        reg[sl] = block
    return reg, made


def grab_parts(reg, hint_parts, img, within, locked, s, margin, soft=()):
    """The parts given boxes, cut out by GrabCut (Rother, Kolmogorov and Blake 2004: colour models fitted inside and
    outside, the boundary a minimum graph cut) inside each part's boxes. The part's points are certainly it, the other
    parts' points certainly not, and nothing outside its boxes (padded by `margin`) is it: a coat boxed apart from the
    face cannot be taken by the skin, whatever its colour. Smaller boxes are cut last, so a print boxed inside a
    shirt's box keeps its own part. The cut is carved into the region map: a region mostly inside one part's cut goes
    to it whole, a region shared by several cuts is split among them; the locked regions (the eyes, the mouth) are left
    alone. A region its drawn lines enclose that holds a part's point is that part's outright, whatever the cuts say
    (a lit cheek inside the face's outline stays the skin's when the hair's cut, over-smoothed in a soft painting,
    reaches into it): the lines are surer than the cut. Only the regions the watershed made (`soft`: where no line
    was found) are left to the cuts. Returns the region map and {region: part index}."""
    h, w = within.shape
    boxed = [k for k, hp in enumerate(hint_parts) if hp.get("boxes")]
    if not boxed:
        return reg, {}
    f = min(1.0, 900.0 / max(h, w))
    sw, sh = max(1, int(w * f)), max(1, int(h * f))
    small = cv2.resize((np.clip(img, 0, 1) * 255).astype(np.uint8), (sw, sh), interpolation=cv2.INTER_AREA)
    small = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
    win_s = cv2.resize(within.astype(np.uint8), (sw, sh), interpolation=cv2.INTER_NEAREST) > 0
    label = np.zeros((h, w), np.int32)
    r_s = max(2, int(round(6 * s * f)))
    # the line-bounded regions under the points, each certainly its point's part
    soft = set(soft)
    pinned = {}
    for q, hp in enumerate(hint_parts):
        for x, y in hp.get("at", []):
            x, y = int(x), int(y)
            if 0 <= y < h and 0 <= x < w and reg[y, x] > 0 and int(reg[y, x]) not in soft:
                pinned[int(reg[y, x])] = q

    def box_mask(boxes, scale, shape, pad):
        m = np.zeros(shape, bool)
        for b in boxes:
            x0, y0, x1, y1 = (int(round(v * scale)) for v in (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad))
            m[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
        return m

    def area(k):
        return sum((b[2] - b[0]) * (b[3] - b[1]) for b in hint_parts[k]["boxes"])

    # every part's point colours, at full size (to settle overlaps) and small (for the cut's starting guess)
    Lf = lab(img)
    full_cols = []
    for hp in hint_parts:
        full_cols.append([np.median(Lf[max(0, int(y) - 3):int(y) + 4, max(0, int(x) - 3):int(x) + 4].reshape(-1, 3), axis=0)
                          for x, y in hp.get("at", []) if 0 <= int(y) < h and 0 <= int(x) < w and within[int(y), int(x)]])
    Ls = lab(cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)
    pcols = []
    for hp in hint_parts:
        cs = []
        for x, y in hp.get("at", []):
            xs_, ys_ = int(x * f), int(y * f)
            if 0 <= ys_ < sh and 0 <= xs_ < sw and win_s[ys_, xs_]:
                cs.append(np.median(Ls[max(0, ys_ - 1):ys_ + 2, max(0, xs_ - 1):xs_ + 2].reshape(-1, 3), axis=0))
        pcols.append(cs)

    def near_colour(cs):
        if not cs:
            return np.full((sh, sw), np.inf, np.float32)
        return np.min(np.stack([tolerant(Ls, c) for c in cs]), axis=0)

    # each part's colour distance where it may be (inside its boxes, or anywhere when it has none): a pink flower on a
    # skirt is not the bouquet's when the bouquet's box is up by the hands
    may = []
    for q, hp in enumerate(hint_parts):
        d = near_colour(pcols[q])
        if hp.get("boxes"):
            d = np.where(box_mask(hp["boxes"], f, (sh, sw), margin), d, np.inf).astype(np.float32)
        may.append(d)

    for k in sorted(boxed, key=area, reverse=True):
        hp = hint_parts[k]
        inside = box_mask(hp["boxes"], f, (sh, sw), margin) & win_s
        # the starting guess inside the boxes: what is nearer in colour to the part's points than to the points of any
        # other part that may be there is probably it, the rest probably not (a turtleneck's box holds the beige lapels
        # beside it); GrabCut then refits both colour models and moves the boundary to the cheapest cut. Two parts of
        # one colour (a white ribbon on white hair) are told apart only by the lines between them, not by their boxes
        mine = near_colour(pcols[k])
        others = [may[q] for q in range(len(hint_parts)) if q != k]
        theirs = np.min(np.stack(others), axis=0) if others else np.full((sh, sw), np.inf, np.float32)
        mask = np.where(inside, np.where(mine <= theirs, cv2.GC_PR_FGD, cv2.GC_PR_BGD), cv2.GC_BGD).astype(np.uint8)
        # a colour clearly another part's is certainly not this one (the steel of a knee plate in a trousers' box):
        # a soft painting's smoothness may not pull it in
        mask[inside & (theirs + 10.0 < mine)] = cv2.GC_BGD
        for q, other in enumerate(hint_parts):
            for x, y in other.get("at", []):
                cv2.circle(mask, (int(x * f), int(y * f)), r_s, cv2.GC_FGD if q == k else cv2.GC_BGD, -1)
        # (the regions pinned by points are not forced either way here: the carving gives a pinned region to its point,
        # but for what another part's cut took that is nearer in colour to that part's points)
        mask[~win_s] = cv2.GC_BGD
        # cut within a window round the boxes: the background's colour model is then learnt from the figure round
        # the part (the coat beside a turtleneck's box), not from the empty picture round the figure
        ys_, xs_ = np.nonzero(inside)
        if not len(ys_):
            continue
        bh, bw = ys_.max() - ys_.min() + 1, xs_.max() - xs_.min() + 1
        y0, y1 = max(0, ys_.min() - bh // 2), min(sh, ys_.max() + 1 + bh // 2)
        x0, x1 = max(0, xs_.min() - bw // 2), min(sw, xs_.max() + 1 + bw // 2)
        win_m = np.ascontiguousarray(mask[y0:y1, x0:x1])
        if not (win_m == cv2.GC_PR_FGD).any() or not (win_m == cv2.GC_BGD).any():
            continue
        # the empty picture inside the window takes the figure's colour nearest it, so it adds no colour of its own
        # to the background's model
        crop = np.ascontiguousarray(small[y0:y1, x0:x1].copy())
        empty = ~win_s[y0:y1, x0:x1]
        if empty.any() and (~empty).any():
            ids = np.where(~empty, np.arange(empty.size).reshape(empty.shape) + 1, 0).astype(np.int32)
            _, near = nearest(ids)
            crop[empty] = crop.reshape(-1, 3)[np.maximum(near[empty] - 1, 0)]
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(crop, win_m, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
        except cv2.error:
            continue
        fg = np.zeros((sh, sw), np.float32)
        fg[y0:y1, x0:x1] = (win_m == cv2.GC_FGD) | (win_m == cv2.GC_PR_FGD)
        full = cv2.resize(fg, (w, h), interpolation=cv2.INTER_LINEAR) > 0.5
        full &= within & box_mask(hp["boxes"], 1.0, (h, w), margin)
        # where an earlier cut took the pixel too, the part whose points are nearer in colour keeps it (a cream
        # bodice inside the skin's chest box stays the dress's)
        conflict = full & (label > 0)
        if conflict.any() and full_cols[k]:
            ys_c, xs_c = np.nonzero(conflict)
            px = Lf[ys_c, xs_c]
            dk = np.min(np.stack([tolerant(px, c) for c in full_cols[k]]), axis=0)
            prev = label[ys_c, xs_c] - 1
            keep = np.zeros(len(prev), bool)
            for j in np.unique(prev):
                if not full_cols[j]:
                    continue
                sel = prev == j
                dj = np.min(np.stack([tolerant(px[sel], c) for c in full_cols[j]]), axis=0)
                keep[sel] = dj < dk[sel]
            full[ys_c[keep], xs_c[keep]] = False
        label[full] = k + 1
    # carve the cuts into the regions
    K = len(hint_parts) + 1
    lock = np.zeros(int(reg.max()) + 1, bool)
    lock[[i for i in locked if i < len(lock)]] = True
    label[lock[reg] | ~within] = 0
    key = reg.astype(np.int64) * K + label
    keys, counts = np.unique(key[within], return_counts=True)
    area_r = np.bincount(reg[within], minlength=int(reg.max()) + 1)
    min_area = max(40.0, 60.0 * s * s)
    nid = int(reg.max())
    remap, owner = {}, {}
    per_region = {}
    for kk, c in zip(keys, counts):
        r, lab_ = int(kk // K), int(kk % K)
        if lab_:
            per_region.setdefault(r, []).append((int(c), lab_ - 1))
    pinned = {r: q for r, q in pinned.items() if not (r < len(lock) and lock[r])}
    for r in pinned:
        per_region.pop(r, None)
    for r, cuts in per_region.items():
        cuts.sort(reverse=True)
        top, k = cuts[0]
        others = sum(c for c, _ in cuts[1:] if c >= min_area)
        if top >= 0.6 * area_r[r] and others == 0:
            owner[r] = k                                   # the region whole
            continue
        for c, k in cuts:
            if c >= min_area:
                nid += 1
                remap[r * K + k + 1] = nid
                owner[nid] = k
    if remap:
        lut_keys = np.array(list(remap.keys()), np.int64)
        lut_vals = np.array(list(remap.values()), np.int64)
        order = np.argsort(lut_keys)
        lut_keys, lut_vals = lut_keys[order], lut_vals[order]
        pos = np.clip(np.searchsorted(lut_keys, key), 0, len(lut_keys) - 1)
        hit = lut_keys[pos] == key
        reg = np.where(hit, lut_vals[pos], reg).astype(np.int32)
    # a pointed region is its point's part, but for what of it the line finder should have shut out (a chest region
    # left open into a cream bodice, a leg's region into the hem): the pixels outside the part's boxes, and the pixels
    # another part's cut took that are clearly nearer in colour to that part's points than to this one's (a lit cheek
    # nearer the skin's points stays the skin's however far the hair's cut reached)
    boxes_of = {q: box_mask(hint_parts[q]["boxes"], 1.0, (h, w), margin) for q in set(pinned.values()) if q in boxed}
    sl_all = ndi.find_objects(reg)
    for r, q in pinned.items():
        owner[r] = q
        if r > len(sl_all) or sl_all[r - 1] is None:
            continue
        sl = sl_all[r - 1]
        mr = reg[sl] == r
        lab_sl = label[sl]
        release = np.zeros(mr.shape, np.int32)                 # 0 keep, -1 nobody's, k + 1 part k's
        if q in boxes_of:
            release[mr & ~boxes_of[q][sl]] = -1
        if full_cols[q]:
            px = Lf[sl]
            mine = np.min(np.stack([tolerant(px, c) for c in full_cols[q]]), axis=0)
            for lv in np.unique(lab_sl[mr]):
                if lv == 0 or lv - 1 == q or not full_cols[lv - 1]:
                    continue
                theirs = np.min(np.stack([tolerant(px, c) for c in full_cols[lv - 1]]), axis=0)
                release[mr & (lab_sl == lv) & (theirs + 5.0 < mine)] = lv
        out_ = mr & (release != 0)
        if out_.sum() < min_area:
            continue
        blk = reg[sl]
        for rv in np.unique(release[out_]):
            piece = out_ & (release == rv)
            if rv == -1:                                       # outside the boxes: the cut there, or nobody
                for lv in np.unique(lab_sl[piece]):
                    sub = piece & (lab_sl == lv)
                    if sub.sum() >= min_area:
                        nid += 1
                        blk[sub] = nid
                        if lv > 0 and lv - 1 != q:
                            owner[nid] = int(lv) - 1
            elif piece.sum() >= min_area:
                nid += 1
                blk[piece] = nid
                owner[nid] = int(rv) - 1
        reg[sl] = blk
    return reg, owner


def claim(hint_parts, reg, st, nb, fig, locked=(), budget=14.0, fixed=None):
    """The parts pointed at (by whoever looked at the picture: "the hair is here, here and here; the skirt here"),
    grown from the regions under the points, all at once, the way a colourist's bucket fills a drawing (scribble
    colouring, as in LazyBrush, Sykora et al. 2009): each region goes to the part that reaches it first, so a navy
    skirt and navy hair pointed at apart stay apart where they meet. A part grows into a touching region of its
    colour that it borders along a good part of its edge or that carries on below it, and into the small shines it
    rings; never into the locked regions (the eyes and the mouth already carved), nor into the regions owned already
    (`fixed`: the parts found in their boxes), nor outside its boxes when it has them. Returns {region: index of the
    hint}."""
    locked = set(locked)
    import heapq
    owner, heap, colour = dict(fixed or {}), [], []
    for k, hp in enumerate(hint_parts):
        # the region under each point is its seed, however small (a point on a line has the line's region, and a
        # line's pixels belong to the region beside them); a point outside the figure has none
        seeds = [int(reg[int(y), int(x)]) for x, y in hp.get("at", [])
                 if 0 <= int(y) < reg.shape[0] and 0 <= int(x) < reg.shape[1] and reg[int(y), int(x)] > 0]
        w_ = np.array([st["area"][j] for j in seeds] or [1.0], np.float64)
        colour.append((st["lab"][seeds] * w_[:, None]).sum(0) / w_.sum() if seeds else np.zeros(3))
        for j in seeds:
            if j not in owner:
                heapq.heappush(heap, (0.0, j, k))
    boxed = {k: hp["boxes"] for k, hp in enumerate(hint_parts) if hp.get("boxes")}

    def in_boxes(q, k):
        return k not in boxed or any(b[0] <= st["cx"][q] <= b[2] and b[1] <= st["cy"][q] <= b[3] for b in boxed[k])

    while heap:
        cost, j, k = heapq.heappop(heap)
        if j in owner:
            continue
        owner[j] = k
        for q in nb.get(j, {}):
            if q == 0 or q in owner or q in locked or not in_boxes(q, k):
                continue
            edge = sum(c for r, c in nb[q].items() if r != 0)
            shared = sum(c for r, c in nb[q].items() if owner.get(r) == k)
            d = cdist(st["lab"][q], colour[k])
            # a small region the part rings is its shine, unless it has the colour of another part named (a white
            # stripe between two navy ones is the white stripes', not a shine of the navy)
            ringed = (shared >= 0.8 * max(edge, 1) and st["area"][q] < 0.01 * fig["area"]
                      and not any(o != k and cdist(st["lab"][q], colour[o]) < d for o in range(len(colour))))
            if not ringed and d > budget:
                continue
            if not ringed and shared < 0.2 * max(edge, 1) and st["area"][q] > 0.002 * fig["area"]:
                sl = st["box"][q - 1]
                group = np.zeros(len(st["area"]), bool)
                group[[r for r, o in owner.items() if o == k]] = True
                width, where = contact(reg, q, group[reg], sl)
                if not (where < 0.3 and width >= 0.5 * (sl[1].stop - sl[1].start)):
                    continue
            heapq.heappush(heap, (cost + 1.0 + d / 10.0, q, k))
    # "within": every other region of the part's colour inside the box given (the scattered motifs of a print,
    # a row of buttons), the way an editor selects similar colours inside a selection
    for k, hp in enumerate(hint_parts):
        if "within" not in hp:
            continue
        x0, y0, x1, y1 = hp["within"]
        for q in range(1, len(st["area"])):
            if q in owner or q in locked or st["area"][q] == 0:
                continue
            if x0 <= st["cx"][q] <= x1 and y0 <= st["cy"][q] <= y1 and cdist(st["lab"][q], colour[k]) <= budget:
                owner[q] = k
    return owner


def point_colours(hp, L, within):
    """The colours under a part's points: the median of a small square round each, so a point a pixel off a line
    still reads its part."""
    h, w = within.shape
    return [np.median(L[max(0, int(y) - 3):int(y) + 4, max(0, int(x) - 3):int(x) + 4].reshape(-1, 3), axis=0)
            for x, y in hp.get("at", []) if 0 <= int(y) < h and 0 <= int(x) < w and within[int(y), int(x)]]


def box_masks(hint_parts, names, shape, pad):
    """Each boxed part's boxes as a mask, a margin of `pad` pixels round each box (keyed by the part's number)."""
    h, w = shape
    out = {}
    for hp in hint_parts:
        if hp.get("boxes") and hp["name"] in names:
            m = np.zeros((h, w), bool)
            for x0, y0, x1, y1 in hp["boxes"]:
                m[max(0, int(y0 - pad)):max(0, int(y1 + pad)), max(0, int(x0 - pad)):max(0, int(x1 + pad))] = True
            out[names[hp["name"]]] = m
    return out


def keep_to_boxes(reg, parts, hint_parts, L, within, pad):
    """The promise the boxes make, kept after every other step: no pixel outside a part's boxes (and a margin of
    `pad` pixels) is that part's. Each piece of a part lying outside its boxes goes to the part whose points are
    nearest in colour among those that may be there (their boxes hold most of the piece, or they have none); a piece
    no other part may hold stays where it was. Regions are cut where their pixels change hands.
    Returns (region map, parts with their region lists renumbered, pixels moved)."""
    names = {p["name"]: i + 1 for i, p in enumerate(parts)}
    own = np.zeros(int(reg.max()) + 1, np.int32)
    for i, p in enumerate(parts, 1):
        own[np.asarray(p["regions"], dtype=np.int64)] = i
    label = own[reg] * (reg > 0)
    allow = box_masks(hint_parts, names, reg.shape, pad)
    seeds = {names[hp["name"]]: point_colours(hp, L, within) for hp in hint_parts if hp["name"] in names}
    moved = 0
    for k, m in allow.items():
        bad = (label == k) & ~m
        if not bad.any():
            continue
        n_, comp = cv2.connectedComponents(bad.astype(np.uint8), connectivity=8)
        for c in range(1, n_):
            pm = comp == c
            col = np.median(L[pm], axis=0)
            best, bd = None, 1e9
            for q, sc in seeds.items():
                if q == k or not sc or (q in allow and allow[q][pm].mean() < 0.5):
                    continue
                d = min(cdist(col, s_) for s_ in sc)
                if d < bd:
                    best, bd = q, d
            if best is not None:
                label[pm] = best
                moved += int(pm.sum())
    if not moved:
        return reg, parts, 0
    key = reg.astype(np.int64) * (len(parts) + 1) + label
    key[reg == 0] = -1
    uniq, inv = np.unique(key, return_inverse=True)
    new = inv.reshape(reg.shape).astype(np.int32) + (0 if uniq[0] == -1 else 1)
    part_of = np.zeros(int(new.max()) + 1, np.int64)
    part_of[new.ravel()] = label.ravel()
    area = np.bincount(new.ravel(), minlength=len(part_of))
    out = []
    for i, p in enumerate(parts, 1):
        ids = np.nonzero(part_of == i)[0]
        ids = [int(r) for r in ids[np.argsort(-area[ids])] if r > 0]
        out.append({**p, "regions": ids})
    return new, [p for p in out if p["regions"]], moved


def boxes_too_small(reg, parts, hint_parts, L, within, pad, height):
    """Where a part runs into the edge of its box and its colour goes on past it, the box was likely drawn too small
    (a leg going on below the knee, a wrist below a sleeve): one doubt per such edge, with the stretch's place."""
    names = {p["name"]: i + 1 for i, p in enumerate(parts)}
    own = np.zeros(int(reg.max()) + 1, np.int32)
    for i, p in enumerate(parts, 1):
        own[np.asarray(p["regions"], dtype=np.int64)] = i
    label = own[reg] * (reg > 0)
    h, w = reg.shape
    out = []
    for hp in hint_parts:
        k = names.get(hp["name"])
        sc = point_colours(hp, L, within)
        if k is None or not hp.get("boxes") or not sc:
            continue
        for b in hp["boxes"]:
            x0, y0 = int(max(0, b[0] - pad)), int(max(0, b[1] - pad))
            x1, y1 = int(min(w - 1, b[2] + pad)), int(min(h - 1, b[3] + pad))
            # (inside line, outside line) for each edge the picture does not cut
            sides = {"left": (np.s_[y0:y1, x0], np.s_[y0:y1, max(0, x0 - 2)]) if x0 > 2 else None,
                     "right": (np.s_[y0:y1, x1], np.s_[y0:y1, min(w - 1, x1 + 2)]) if x1 < w - 3 else None,
                     "top": (np.s_[y0, x0:x1], np.s_[max(0, y0 - 2), x0:x1]) if y0 > 2 else None,
                     "bottom": (np.s_[y1, x0:x1], np.s_[min(h - 1, y1 + 2), x0:x1]) if y1 < h - 3 else None}
            for side, sl in sides.items():
                if sl is None:
                    continue
                ins, outs = sl
                lab_o = L[outs].reshape(-1, 3)
                d = np.min([np.hypot(lab_o[:, 1] - s_[1], lab_o[:, 2] - s_[2]) + 0.6 * np.abs(lab_o[:, 0] - s_[0])
                            for s_ in sc], axis=0)
                go_on = (label[ins] == k) & within[outs] & (label[outs] != k) & (d < 10)
                if go_on.sum() >= 0.015 * height:
                    out.append(f"part '{hp['name']}' seems to go on past the {side} edge of its box {list(b)} "
                               f"({int(go_on.sum())} px of its colour there): draw the box larger if it does")
    return out


def same_colour_parts(parts, hint_parts, L, within, nb, s, near=10.0):
    """Two named parts of nearly the same colour that touch (blue-grey hair over a pale blue cardigan, a beige coat on
    beige skin): no colour tells them apart, so where one ends follows the boxes and the lines alone, and a box's
    straight edge can cut a lock of hair. One doubt per such pair, so a reviewer looks along that border first."""
    cols = {}
    for hp in hint_parts:
        pc = point_colours(hp, L, within)
        if pc:
            cols[hp["name"]] = np.median(np.array(pc), axis=0)
    regs = {p["name"]: set(p["regions"]) for p in parts}
    names = [n for n in cols if n in regs]
    out = []
    for i, a_ in enumerate(names):
        for b_ in names[i + 1:]:
            if "hair" in (a_, b_):
                continue                               # (the hair's own doubt, below, covers it)
            d = cdist(cols[a_], cols[b_])
            if d >= near:
                continue
            touch = sum(c for r in regs[a_] for j, c in nb.get(r, {}).items() if j in regs[b_])
            if touch > 30 * s:
                out.append(f"parts '{a_}' and '{b_}' are nearly the same colour (a difference of {d:.0f}) and touch: "
                           "no colour tells them apart, so their border follows the boxes and the lines; look along "
                           "it on the parts sheet, and give points on both sides of it where it goes wrong")
    return out


def two_colour_regions(reg, L, core, st, parts, fig, min_share=0.01, iters=12):
    """Regions holding two colours far apart, each in a piece of its own (an orange jacket and navy trousers, dark
    brown shoes and navy trousers): a gap in a line let two materials run together, and whatever the region is named
    is wrong for half of it. Two colours are far apart when both are colourful and their hues differ by more than 60
    degrees (more than 90 when one is barely coloured, a dark brown), or one is colourful and the other a grey of
    another lightness; a garment's lit and shaded tones, hue-shifted or not, are neither. Hair and skin, whose shadows
    are often drawn in another hue on purpose, are left out. One doubt per region."""
    kind_of_reg = {int(i): p["kind"] for p in parts for i in p["regions"]}
    rng = np.random.default_rng(0)
    out = []
    for i in np.flatnonzero(st["area"] >= min_share * fig["area"]):
        if i == 0 or kind_of_reg.get(int(i)) in ("eyes", "accessory", "hair", "skin") or st["box"][i - 1] is None:
            continue
        bx = st["box"][i - 1]
        m = (reg[bx] == i) & core[bx]
        px = L[bx][m].astype(np.float64)
        if len(px) < 400:
            continue
        smp = px[rng.choice(len(px), min(len(px), 4000), replace=False)]
        c = [smp[np.argmax(((smp - smp.mean(0)) ** 2).sum(1))]]
        c.append(smp[np.argmax(((smp - c[0]) ** 2).sum(1))])
        c = np.array(c)
        for _ in range(iters):                          # two-means from the two most distant colours
            k = (((smp[:, None] - c[None]) ** 2).sum(2)).argmin(1)
            if (k == 0).all() or (k == 1).all():
                break
            c = np.array([smp[k == j].mean(0) for j in (0, 1)])
        share = np.bincount(k, minlength=2) / len(smp)
        if share.min() < 0.12:
            continue
        ca, cb = c
        hue_gap = abs((hue(ca) - hue(cb) + 180) % 360 - 180)
        lo, hi = sorted((chroma(ca), chroma(cb)))
        if not ((lo > 10 and hue_gap > 60) or (lo > 6 and hue_gap > 90)
                or (hi > 20 and lo < 8 and abs(ca[0] - cb[0]) > 30)):
            continue
        whole = (((px[:, None] - c[None]) ** 2).sum(2)).argmin(1)
        pieced = True
        for j in (0, 1):                                # each colour mostly one piece, not speckle or stripes
            mj = np.zeros(m.shape, np.uint8)
            mj[m] = whole == j
            n_, lab_, cst, _ = cv2.connectedComponentsWithStats(mj, connectivity=8)
            if n_ < 2 or cst[1:, cv2.CC_STAT_AREA].max() < 0.6 * mj.sum():
                pieced = False
        if pieced:
            out.append(f"region {int(i)} holds two colours far apart ({colour_word(ca)} and {colour_word(cb)}, "
                       f"{100 * st['area'][i] / fig['area']:.1f} % of the figure): a gap in a line let two materials "
                       "run together; give a point on each so they are cut apart")
    return out


def families_of(ids, st, nb, height, t_adj=8.0, t_fam=12.0):
    """The remaining regions grouped: touching regions of nearly one colour joined (the folds of one garment), then
    the groups of one colour joined wherever they are side by side (the two sleeves, the two shoes), the largest
    first; but one colour far apart up and down is two things (a belt and the boots of its leather): a family is
    split where a gap of a tenth of the figure's height runs between its groups. A print (a small group whose edge is
    almost all one other group: keyholes on trousers, a star on a hoodie) joins only the prints on the same ground,
    not a garment elsewhere that happens to share its colour; its family is marked as a print."""
    ids = list(ids)
    parent = {i: i for i in ids}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    idset = set(ids)
    for i in ids:
        for j in nb.get(i, {}):
            if j in idset and j > i and cdist(st["lab"][i], st["lab"][j]) <= t_adj:
                ri, rj = root(i), root(j)
                if ri != rj:
                    parent[rj] = ri
    groups = {}
    for i in ids:
        groups.setdefault(root(i), []).append(i)

    def colour(g):
        a = np.array([st["area"][i] for i in g], np.float64)
        return (st["lab"][g] * a[:, None]).sum(0) / a.sum()

    glist = sorted(groups.values(), key=lambda g: -sum(st["area"][i] for i in g))
    gid = {i: k for k, g in enumerate(glist) for i in g}
    garea = [sum(st["area"][i] for i in g) for g in glist]

    def ground(k):
        """The group a small group sits on, when nearly all its edge is that one group's."""
        edge = {}
        for i in glist[k]:
            for j, c in nb.get(i, {}).items():
                kj = gid.get(j)
                if kj != k:
                    key = kj if kj is not None else -1 - j        # a region of the skin, the hair or the outside
                    edge[key] = edge.get(key, 0) + c
        if not edge:
            return None
        best = max(edge, key=edge.get)
        if best >= 0 and edge[best] >= 0.7 * sum(edge.values()) and garea[k] < 0.1 * garea[best]:
            return best
        return None

    fams = []
    for k, g in enumerate(glist):
        c = colour(np.array(g))
        on = ground(k)
        for fam in fams:
            if fam["on"] == on and cdist(c, fam["colour"]) <= t_fam:
                fam["groups"].append(g)
                break
        else:
            fams.append({"groups": [g], "colour": c, "on": on})
    out = []
    for fam in fams:
        spans = sorted(((min(st["box"][i - 1][0].start for i in g), max(st["box"][i - 1][0].stop for i in g)), g)
                       for g in fam["groups"])
        cur, bottom = [], -1
        for (top, bot), g in spans:
            if cur and top - bottom > 0.1 * height:
                out.append((cur, fam["on"]))
                cur = []
            cur += g
            bottom = max(bottom, bot)
        out.append((cur, fam["on"]))
    return [{"regions": r, "colour": colour(np.array(r)), "print": on is not None} for r, on in out]


def kind_for(fam, st, fig):
    """A clothing part's kind from its colour, its size and its place."""
    regs = np.array(fam["regions"])
    a = st["area"][regs].astype(np.float64)
    share = a.sum() / fig["area"]
    L50 = float(np.average(st["L50"][regs], weights=a))
    L90 = float(np.average(st["L90"][regs], weights=a))
    L10 = float(np.average(st["L10"][regs], weights=a))
    c = fam["colour"]
    low = float(np.average(st["cy"][regs], weights=a) - fig["y_top"]) / fig["height"]
    if L50 < 13 and L90 < 24:
        return "accessory", "pure black: kept as drawn"
    if fam.get("print"):
        return "accessory", "a print on another part: kept as drawn"
    if share < 0.004:
        return "accessory", "small: kept as drawn"
    if 65 <= hue(c) <= 105 and chroma(c) > 28 and L90 - L10 > 25 and share < 0.03:
        return "metal", "gold"
    if L50 < 40 and low > 0.85 and L90 - L50 > 22:
        return "gloss", "dark with shines, at the feet"
    if L50 < 40:
        return "cloth-dark", ""
    if L50 > 80 and chroma(c) < 12:
        return "cloth-white", ""
    return "cloth", ""


def samples(regs, reg, n=3):
    """A few points deep inside a part's largest regions, for its colour family."""
    pts = []
    sl = ndi.find_objects(reg)
    for i in regs[:n]:
        s = sl[i - 1]
        if s is None:
            continue
        m = (reg[s] == i).astype(np.uint8)
        d = cv2.distanceTransform(np.pad(m, 1), cv2.DIST_L2, 3)[1:-1, 1:-1]
        y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        pts.append([int(s[1].start + x), int(s[0].start + y)])
    return pts


# ------------------------------------------------------------------------------------------------------------ review

def parts_sheet(img, alpha, reg, parts, path, fig_area):
    """Every part on its own: the figure with only that part's pixels in their own colours (the rest pale), its name,
    kind and share. Mixed materials show at once (white frills inside a pink dress), where the false colours of the
    review picture may hide them."""
    h, w = reg.shape
    bgr = over(img, alpha)
    pale = (bgr.astype(np.float32) * 0.18 + 235 * 0.82).astype(np.uint8)
    ys, xs = np.nonzero(alpha > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    th = 420
    z = th / float(y1 - y0)
    tw = max(60, int((x1 - x0) * z))
    tiles = []
    for p in parts:
        lut = np.zeros(int(reg.max()) + 1, bool)
        lut[p["regions"]] = True
        m = lut[reg]
        if not m.any():
            continue
        t = np.where(m[..., None], bgr, pale)[y0:y1, x0:x1]
        t = cv2.resize(t, (tw, th), interpolation=cv2.INTER_AREA)
        # a thin ring round the part's pixels, so small pieces show at this size
        mm = cv2.resize(m[y0:y1, x0:x1].astype(np.uint8), (tw, th), interpolation=cv2.INTER_NEAREST)
        ring = (cv2.dilate(mm, np.ones((3, 3), np.uint8)) > 0) & (mm == 0)
        t[ring] = (40, 40, 230)
        head = np.full((40, tw, 3), 255, np.uint8)
        cv2.putText(head, p["name"][:18], (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)
        cv2.putText(head, f"{p['kind']} {100 * m.sum() / fig_area:.1f}%", (4, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (90, 90, 90), 1)
        tiles.append(np.vstack([head, t]))
    if not tiles:
        return
    per = max(1, min(8, 1600 // (tw + 8)))
    rows = []
    for i in range(0, len(tiles), per):
        row = tiles[i:i + per]
        row += [np.full_like(tiles[0], 255)] * (per - len(row))
        rows.append(np.hstack([np.pad(t, ((0, 8), (0, 8), (0, 0)), constant_values=255) for t in row]))
    cv2.imwrite(str(path), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


def review(img, alpha, reg, parts, path, face_path, boxes, face_box):
    h, w = reg.shape
    n = len(parts)
    pal = np.array([KELLY[i % len(KELLY)][::-1] for i in range(n + 1)], np.uint8)
    plab = np.zeros(int(reg.max()) + 1, np.int32)
    for j, p in enumerate(parts, start=1):
        plab[p["regions"]] = j
    pm = plab[reg]
    bgr = over(img, alpha).astype(np.float32)
    vis = (bgr * 0.45 + pal[pm].astype(np.float32) * 0.55).astype(np.uint8)
    vis[alpha < 0.5] = (236, 236, 236)
    edge = np.zeros((h, w), bool)
    edge[:, 1:] |= pm[:, 1:] != pm[:, :-1]
    edge[1:, :] |= pm[1:, :] != pm[:-1, :]
    vis[edge] = (40, 40, 40)
    out = vis.copy()
    for b in boxes:
        cv2.rectangle(out, (b[0], b[1]), (b[2], b[3]), (40, 40, 230), 2)
    sl = ndi.find_objects(reg)
    s = min(1.0, 2200.0 / h)
    small = cv2.resize(out, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    def numbers(canvas, scale, ox, oy, min_px, font):
        for i, sli in enumerate(sl, start=1):
            if sli is None:
                continue
            m = (reg[sli] == i).astype(np.uint8)
            if m.sum() * scale * scale < min_px:
                continue
            d = cv2.distanceTransform(np.pad(m, 1), cv2.DIST_L2, 3)[1:-1, 1:-1]
            y, x = np.unravel_index(int(np.argmax(d)), d.shape)
            px, py = int((sli[1].start + x - ox) * scale), int((sli[0].start + y - oy) * scale)
            if 0 <= px < canvas.shape[1] and 0 <= py < canvas.shape[0]:
                cv2.putText(canvas, str(i), (px - 6, py + 4), cv2.FONT_HERSHEY_SIMPLEX, font, (255, 255, 255), 3)
                cv2.putText(canvas, str(i), (px - 6, py + 4), cv2.FONT_HERSHEY_SIMPLEX, font, (20, 20, 20), 1)

    numbers(small, s, 0, 0, 260, 0.42)
    grid(small, s, 0, 0, 100 if h <= 4000 else 200)
    legend = np.full((max(small.shape[0], 30 + 24 * n), 330, 3), 255, np.uint8)
    for j, p in enumerate(parts, start=1):
        cv2.rectangle(legend, (10, 10 + (j - 1) * 24), (30, 28 + (j - 1) * 24), tuple(int(v) for v in pal[j]), -1)
        cv2.putText(legend, f"{p['name']} ({p['kind']})", (38, 25 + (j - 1) * 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (30, 30, 30), 1)
    small = np.vstack([small, np.full((legend.shape[0] - small.shape[0], small.shape[1], 3), 255, np.uint8)]) \
        if legend.shape[0] > small.shape[0] else small
    cv2.imwrite(str(path), np.hstack([small, legend[:small.shape[0]]]), [cv2.IMWRITE_JPEG_QUALITY, 90])
    if face_box:
        x0, y0, x1, y1 = pad_box(face_box, 0.25, 10, h, w)
        z = min(4.0, 1400.0 / max(1, max(x1 - x0, y1 - y0)))
        crop = cv2.resize(out[y0:y1, x0:x1], None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)
        src = cv2.resize(bgr[y0:y1, x0:x1].astype(np.uint8), None, fx=z, fy=z, interpolation=cv2.INTER_CUBIC)
        numbers(crop, z, x0, y0, 120, 0.5)
        grid(src, z, x0, y0, 50 if (x1 - x0) <= 800 else 100)
        grid(crop, z, x0, y0, 50 if (x1 - x0) <= 800 else 100)
        cv2.imwrite(str(face_path), np.hstack([src, crop]), [cv2.IMWRITE_JPEG_QUALITY, 90])


def grid(canvas, scale, ox, oy, step):
    """Light lines every `step` pixels of the picture, numbered in the picture's own pixels, so whoever reviews it
    can read off where things are (to point at a part, to box an eye)."""
    h, w = canvas.shape[:2]
    for x in range(int(np.ceil(ox / step)) * step, int(ox + w / scale) + 1, step):
        px = int((x - ox) * scale)
        cv2.line(canvas, (px, 0), (px, h - 1), (150, 150, 255), 1)
        cv2.putText(canvas, str(x), (px + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (40, 40, 200), 1)
    for y in range(int(np.ceil(oy / step)) * step, int(oy + h / scale) + 1, step):
        py = int((y - oy) * scale)
        cv2.line(canvas, (0, py), (w - 1, py), (150, 150, 255), 1)
        cv2.putText(canvas, str(y), (2, py - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (40, 40, 200), 1)


# -------------------------------------------------------------------------------------------------------------- main

def like_parts(parts, ref_path, st, fig):
    """Names and kinds from another subject of the same character: each part takes the name and kind of the reference
    part of its colour (and of its kind, for the skin, the hair and the eyes); parts that land on one name join."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _style import load_subject, kind_of
    from parts import load_or_build
    rs = load_subject(ref_path)
    rimg, ralpha, rparts = load_or_build(rs)
    RL = lab(rimg)
    refs = []
    for j, p in enumerate(rs["parts"], start=1):
        m = (rparts == j) & (ralpha > 0.8)
        if m.sum() < 30:
            continue
        refs.append((p["name"], kind_of(p), np.median(RL[m], axis=0)))
    semantic = ("skin", "hair", "eyes")
    out = {}
    for p in parts:
        c = p["_colour"]
        cands = [r for r in refs if (r[1] == p["kind"] if p["kind"] in semantic else r[1] not in semantic)]
        best = min(cands, key=lambda r: cdist(c, r[2]), default=None)
        if best is not None and cdist(c, best[2]) <= 12:
            p = dict(p, name=best[0], kind=best[1])
        if p["name"] in out:
            out[p["name"]]["regions"] += p["regions"]
        else:
            out[p["name"]] = p
    return list(out.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("subject")
    ap.add_argument("--upscaled", type=int, default=1, help="how many times the picture was enlarged (scripts/prep.py)")
    ap.add_argument("--head-px", type=float, help="the head's height in pixels, for a figure the frame cuts off")
    ap.add_argument("--like", help="another subject of the same character: its part names and kinds are reused")
    ap.add_argument("--hints", help="what someone who looked at the picture pointed at: rough eye and mouth boxes, "
                                    "points on parts (references/subject-file.md)")
    a = ap.parse_args()
    hints = {}
    if a.hints:
        try:
            hints = json.loads(Path(a.hints).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            die(f"cannot read the hints {a.hints}: {e}")
        for hp in hints.get("parts", []):
            if "box" in hp:
                hp["boxes"] = hp.get("boxes", []) + [hp.pop("box")]
    img, alpha = load_rgba(a.image)
    h, w = alpha.shape
    within = alpha > 0.5
    if within.sum() < 1000:
        die(f"{a.image}: the figure is too small or the picture is fully transparent")
    U = Units(alpha, a.head_px)
    L = lab(img)
    ys = np.nonzero(within.any(axis=1))[0]
    fig = {"within": within, "L": L, "area": float(within.sum()), "y_top": float(ys[0]),
           "height": float(ys[-1] - ys[0] + 1)}

    # 1. the regions the lines enclose
    s = U.s
    reg, line, core = regions_of(img, within, L, s, a.upscaled)
    doubts = []

    # 2. the face, found in the pixels; its eyes and its mouth carved into regions of their own
    face = find_face(L, within, reg, line, fig, s, hints)
    carved = {"white": [], "iris": [], "mouth": [], "black": []}
    # pure-black masses on light ground (a chin's cast shadow drawn in black, a black print on a white shirt) are carved
    # out as a kept part of their own, so no style paints them in the colours of the light part round them; black on
    # dark ground (the deep shadows of black hair or a black coat) stays with its part
    black = (L[..., 0] < 14) & within
    mass = cv2.morphologyEx(black.astype(np.uint8), cv2.MORPH_OPEN, disk(max(1, 2.5 * s)))
    k_m, cc_m, st_m, _ = cv2.connectedComponentsWithStats(mass, connectivity=8)
    if k_m > 1:
        nid = int(reg.max())
        ring_k = disk(max(2, 4 * s))
        for c in range(1, k_m):
            x, y, bw, bh, area_m = (int(v) for v in st_m[c])
            if area_m < 60 * s * s:
                continue
            pad = int(8 * s) + 2
            sl = (slice(max(0, y - pad), y + bh + pad), slice(max(0, x - pad), x + bw + pad))
            m_ = (cc_m[sl] == c).astype(np.uint8)
            ring = (cv2.dilate(m_, ring_k) > 0) & (m_ == 0) & within[sl] & ~black[sl]
            if ring.sum() < 20 or float(np.median(L[sl][..., 0][ring])) <= 45:
                continue
            piece = black[sl] & (cv2.dilate(m_, disk(2)) > 0)
            nid += 1
            blk = reg[sl]
            blk[piece] = nid
            reg[sl] = blk
            carved["black"].append(nid)
        reg, lut = relabel(reg, with_lut=True)
        carved = {k: [int(lut[i]) for i in v if i < len(lut) and lut[i] > 0] for k, v in carved.items()}
    if face is not None:
        skin_c = face["colour"]
        nid = int(reg.max())
        for e in face["eyes"]:
            m = e["mask"] & within
            white = m & (L[..., 0] > 60) & (np.hypot(L[..., 1], L[..., 2]) < max(6.0, 0.7 * chroma(skin_c)))
            for key, mm in (("white", white), ("iris", m & ~white)):
                if mm.sum() >= 12 * s * s:
                    nid += 1
                    reg[mm] = nid
                    carved[key].append(nid)
        if face["mouth"] is not None:
            mm = face["mouth"][1] & within & ~face["head"]
            if mm.sum() >= 30 * s * s:
                nid += 1
                reg[mm] = nid
                carved["mouth"].append(nid)
        # a region partly on the skin and partly off it (a face and its hair joined where a line is faint, as in a
        # picture graded to night) is split in two along the skin's edge
        on = cv2.morphologyEx((skin_of(L, skin_c) & within).astype(np.uint8), cv2.MORPH_OPEN, disk(max(1, 1.5 * s))) > 0
        area_r = np.bincount(reg.ravel(), minlength=nid + 1)
        share = np.bincount(reg[on], minlength=nid + 1) / np.maximum(area_r, 1)
        mixed = (share >= 0.15) & (share <= 0.85) & (area_r >= 400 * s * s)
        mixed[0] = False
        for key in carved:
            mixed[carved[key]] = False
        cut = mixed[reg] & ~on & within
        reg[cut] = reg[cut] + nid
        reg, lut = relabel(reg, with_lut=True)
        carved = {k: [int(lut[i]) for i in v if lut[i] > 0] for k, v in carved.items()}
    grabbed = {}
    if hints.get("parts"):
        # the figure's own outline is line art too, though over the transparent (black) ground the line finder does not
        # see it: found once more over a white ground, near the figure's edge
        edge_d = cv2.distanceTransform(within.astype(np.uint8), cv2.DIST_L2, 3)
        rim = find_lines(img * alpha[..., None] + (1 - alpha[..., None]), a.upscaled) > 0.3
        reg, soft = split_by_hints(reg, hints["parts"], L, s, line=line | (rim & within & (edge_d < 10 * s)))
        reg, lut = relabel(reg, with_lut=True)
        carved = {k: [int(lut[i]) for i in v if i < len(lut) and lut[i] > 0] for k, v in carved.items()}
        soft = {int(lut[i]) for i in soft if i < len(lut) and lut[i] > 0}
        # the parts given boxes: cut out inside their boxes, the cut carved into the regions
        reg, grabbed = grab_parts(reg, hints["parts"], img, within, [i for v in carved.values() for i in v], s,
                                  0.015 * fig["height"], soft)
        if grabbed:
            reg, lut = relabel(reg, with_lut=True)
            carved = {k: [int(lut[i]) for i in v if i < len(lut) and lut[i] > 0] for k, v in carved.items()}
            grabbed = {int(lut[i]): k for i, k in grabbed.items() if i < len(lut) and lut[i] > 0}
    st = region_stats(reg, L, core)
    nb = neighbours(adjacency(reg))
    n = int(reg.max())
    taken = np.zeros(n + 1, bool)
    for ids in carved.values():
        taken[ids] = True
    parts = []
    protect, focal, blush = [], [], []
    if face is None:
        if hints.get("eyes"):
            # the face hidden (a mask, a hood) or turned away: the boxes given are the eyes and the mouth
            for k_, b in enumerate(hints["eyes"]):
                protect.append({"name": ("left eye", "right eye")[k_] if len(hints["eyes"]) == 2 else "eye",
                                "box": pad_box(b, 0.1, 2 * s, h, w)})
            if hints.get("mouth"):
                protect.append({"name": "mouth", "box": pad_box(hints["mouth"], 0.1, 2 * s, h, w), "de": 6})
            doubts.append("no face found in the skin: the eye and mouth boxes given are used as they are")
        else:
            doubts.append("no face found: there are no skin, hair or eyes parts; give them by hand")
    else:
        eyes, X = face["eyes"], face["X"]
        if any(e.get("given") for e in eyes):
            doubts.append("no eyes read in the face (glasses? closed eyes?): the eye boxes given are used as they are; "
                          "check them on the face sheet")
        if not eyes:
            doubts.append("no clear eyes in the face (glasses? closed eyes?): add the eye boxes by hand")
        elif len(eyes) < 2:
            doubts.append("1 eye found in the face: check the eye boxes and parts")
        for k_, e in enumerate(eyes):
            protect.append({"name": ("left eye", "right eye")[k_] if len(eyes) == 2 else "eye",
                            "box": pad_box(e["box"], 0.15, 4 * s, h, w)})
        if face["mouth"] is not None:
            # a box given is rough already: only a hair's margin round it
            mpad = (0.0, 2 * s) if hints.get("mouth") else (0.2, 4 * s)
            protect.append({"name": "mouth", "box": pad_box(face["mouth"][0], *mpad, h, w), "de": 6})
        elif eyes:
            doubts.append("no mouth found: add its box (de 6) by hand if it shows")
        # the skin: the regions mostly on the face's skin, then every region of the skin's colour
        on_head = np.bincount(reg[face["head"]], minlength=n + 1)
        face_regs = {i for i in range(1, n + 1) if not taken[i] and on_head[i] >= 0.5 * st["area"][i]
                     and is_skin(st["lab"][i], skin_c, 18.0)}
        hx0, hy0, hx1, _ = face["box"]
        eye_y = sum(e["centre"][1] for e in eyes) / len(eyes) if eyes else hy0 + 0.35 * X
        hair, hair_c = grow_hair(reg, face_regs, eye_y, X, skin_c, st, nb, fig, taken)
        if not hair:
            doubts.append("no hair found round the face: give the hair part by hand")
        taken[list(hair)] = True
        skin = set(face_regs)
        for i in range(1, n + 1):
            c = st["lab"][i]
            near_hair = hair_c is not None and cdist(c, skin_c, 0.6) >= cdist(c, hair_c)
            if not taken[i] and i not in skin and is_skin(c, skin_c) and not near_hair:
                skin.add(i)
        taken[list(skin)] = True
        parts.append({"name": "skin", "kind": "skin", "regions": sorted(skin, key=lambda i: -st["area"][i])})
        if hair:
            parts.append({"name": "hair", "kind": "hair", "regions": sorted(hair, key=lambda i: -st["area"][i])})
        for key, name in (("white", "eye-whites"), ("iris", "irises")):
            if carved[key]:
                parts.append({"name": name, "kind": "eyes", "regions": carved[key]})
        if carved["mouth"]:
            parts.append({"name": "mouth", "kind": "accessory", "regions": carved["mouth"]})
        # the face's focal area, the blush spots under the eyes, the hands
        ex = sum(e["centre"][0] for e in eyes) / len(eyes) if eyes else (hx0 + hx1) / 2
        span = abs(eyes[-1]["centre"][0] - eyes[0]["centre"][0]) if len(eyes) == 2 else 0.45 * X
        focal.append({"name": "face", "centre": [int(ex), int(eye_y + 0.35 * span)],
                      "radii": [int(0.75 * X), int(0.85 * X)], "strength": 1.0})
        # the blush on the cheeks: measured from the eyes' centres by the span between them, so an eye box drawn large
        # (a brow or lashes inside it) does not push the blush down to the mouth
        for e in eyes:
            side = -1 if e["centre"][0] < ex else 1
            blush.append([int(e["centre"][0] + side * 0.08 * span), int(e["centre"][1] + 0.42 * span),
                          int(0.2 * span), int(0.09 * span)])
        sk = np.zeros(n + 1, bool)
        sk[list(skin)] = True
        k_, cc, cst, _ = cv2.connectedComponentsWithStats((sk[reg] & ~face["head"]).astype(np.uint8), connectivity=8)
        fa = float(face["head"].sum())
        hands = sorted((int(cst[c, cv2.CC_STAT_AREA]), c) for c in range(1, k_)
                       if 0.06 * fa <= cst[c, cv2.CC_STAT_AREA] <= 0.7 * fa)
        for _, c in hands[-2:]:
            bx, by, bw, bh, _ = (int(v) for v in cst[c])
            focal.append({"name": "hand", "centre": [bx + bw // 2, by + bh // 2],
                          "radii": [max(10, int(0.7 * bw)), max(10, int(0.7 * bh))], "strength": 0.7})

    if carved["black"]:
        parts.append({"name": "black-masses", "kind": "accessory", "regions": carved["black"],
                      "_why": "pure black on light ground: kept as drawn"})

    # 3. the rest by colour, each family a part with a kind
    rest = [i for i in range(1, n + 1) if not taken[i]]
    used = {p["name"] for p in parts}
    for fam in families_of(rest, st, nb, fig["height"]):
        kind, why = kind_for(fam, st, fig)
        base = "ink" if why.startswith("pure black") else colour_word(fam["colour"]) + ("-print" if fam.get("print") else "")
        name, k_ = base, 2
        while name in used:
            name, k_ = f"{base}-{k_}", k_ + 1
        used.add(name)
        parts.append({"name": name, "kind": kind, "regions": sorted(fam["regions"], key=lambda i: -st["area"][i]),
                      **({"_why": why} if why else {})})
    # the parts pointed at take their regions from whatever part the draft gave them to
    if hints.get("parts"):
        locked = [i for v in carved.values() for i in v]
        owner = claim(hints["parts"], reg, st, nb, fig, locked=locked, fixed=grabbed)
        if hints.get("complete"):
            # the reviewer named every part: what no point reached joins a touching named part by seeded region
            # growing (Adams and Bischof 1994): of all the unclaimed regions touching a part, the one nearest in colour
            # to that part's points joins first, so a white sleeve touching both a navy stripe and a white collar
            # goes to the collar whichever it is looked at from; what touches none goes to the nearest part in place;
            # the draft's own parts (but the eyes and the mouth found in the face) are dropped
            import heapq
            seeds_c = []
            for hp in hints["parts"]:
                cs = [np.median(L[max(0, int(y) - 3):int(y) + 4, max(0, int(x) - 3):int(x) + 4].reshape(-1, 3), axis=0)
                      for x, y in hp.get("at", []) if 0 <= int(y) < h and 0 <= int(x) < w and within[int(y), int(x)]]
                seeds_c.append(cs)

            pad_b = 0.015 * fig["height"]

            def to_part(i, k):
                # a part given boxes takes nothing whose middle lies outside them
                boxes = hints["parts"][k].get("boxes")
                if boxes and not any(b[0] - pad_b <= st["cx"][i] <= b[2] + pad_b and
                                     b[1] - pad_b <= st["cy"][i] <= b[3] + pad_b for b in boxes):
                    return 1e9
                return min((cdist(st["lab"][i], c) for c in seeds_c[k]), default=1e9)

            lockset = set(locked)
            rest_ids = {i for i in range(1, n + 1) if i not in owner and i not in lockset and st["area"][i] > 0}
            heap = []
            for i in rest_ids:
                for j in nb.get(i, {}):
                    if j in owner:
                        heapq.heappush(heap, (to_part(i, owner[j]), i, owner[j]))
            while heap:
                d, i, k = heapq.heappop(heap)
                if i not in rest_ids:
                    continue
                if d > 20:
                    # nothing it touches is its colour: the named part of its colour wherever that is (a sleeve cut
                    # off from its shirt by a collar's stripe), when there is one
                    kg = min(range(len(seeds_c)), key=lambda q: to_part(i, q))
                    if to_part(i, kg) <= 20:
                        k = kg
                    elif d >= 1e9:
                        continue                           # outside the boxes of every part touching it
                owner[i] = k
                rest_ids.discard(i)
                for j in nb.get(i, {}):
                    if j in rest_ids:
                        heapq.heappush(heap, (to_part(j, k), j, k))
            if rest_ids:
                hl = np.zeros(n + 1, np.int32)
                for i, k in owner.items():
                    hl[i] = k + 1
                _, near_lab = nearest(hl[reg] * (reg > 0))
                for i in rest_ids:
                    ys_, xs_ = np.nonzero(reg == i)
                    if len(ys_) and near_lab[ys_[0], xs_[0]] > 0:
                        owner[i] = int(near_lab[ys_[0], xs_[0]]) - 1
            keep = {"eye-whites", "irises", "mouth", "black-masses"} - {hp["name"] for hp in hints["parts"]}
            draft = {p["name"]: p for p in parts}
            # the colours' reading against the reviewer's: a large region the face says is skin or hair, named
            # otherwise
            for name, kind in (("skin", "skin"), ("hair", "hair")):
                for i in draft.get(name, {}).get("regions", []):
                    k = owner.get(i)
                    if k is not None and hints["parts"][k].get("kind") not in (kind, None) and \
                            st["area"][i] > 0.005 * fig["area"]:
                        sl = st["box"][i - 1]
                        doubts.append(f"region {i} reads as {kind} but was named '{hints['parts'][k]['name']}': "
                                      f"check at [{sl[1].start}, {sl[0].start}, {sl[1].stop}, {sl[0].stop}]")
            parts = [p for p in parts if p["name"] in keep]
        for p in parts:
            p["regions"] = [i for i in p["regions"] if i not in owner]
        by_name = {p["name"]: p for p in parts}
        for k, hp in enumerate(hints["parts"]):
            mine = sorted((i for i, o in owner.items() if o == k), key=lambda i: -st["area"][i])
            if hp["name"] in by_name:
                q = by_name[hp["name"]]
                q["regions"] = mine + q["regions"]
                q["kind"] = hp.get("kind", q["kind"])
            else:
                q = {"name": hp["name"], "kind": hp.get("kind", "cloth"), "regions": mine}
                parts.append(q)
                by_name[q["name"]] = q
            if not mine:
                doubts.append(f"the points for '{hp['name']}' reached no region: check where they lie")
            for x, y in hp.get("at", []):
                if not (0 <= int(y) < h and 0 <= int(x) < w and within[int(y), int(x)]):
                    doubts.append(f"the point {[int(x), int(y)]} for '{hp['name']}' lies outside the figure "
                                  "(scripts/hints.py check shows where each point lands)")
        parts = [p for p in parts if p["regions"]]
        # the boxes' promise kept whatever the steps before did: nothing outside a part's boxes is that part
        reg, parts, moved = keep_to_boxes(reg, parts, hints["parts"], L, within, 0.005 * fig["height"])
        if moved:
            st = region_stats(reg, L, core)
            nb = neighbours(adjacency(reg))
            n = int(reg.max())
        doubts += boxes_too_small(reg, parts, hints["parts"], L, within, 0.005 * fig["height"], fig["height"])
        doubts += same_colour_parts(parts, hints["parts"], L, within, nb, s)
    parts = [p for p in parts if p["regions"]]
    for p in parts:
        r = np.array(p["regions"], dtype=np.int64)
        a_ = st["area"][r].astype(np.float64)
        p["_colour"] = (st["lab"][r] * a_[:, None]).sum(0) / a_.sum()
    if a.like:
        parts = like_parts(parts, a.like, st, fig)

    # 4. what to look at first: parts of two colours, hair that meets clothes of its colour
    for p in parts:
        r = np.array(p["regions"])
        if len(r) < 2 or p["kind"] in ("eyes", "accessory"):
            continue
        # the regions far from the part's main colour, grouped by their colour's name, the largest group first, with
        # their share of the figure: "part 'dress' (pink) holds white regions 981, 966 (2.3 % of the figure)"
        odd = {}
        for i in r:
            if cdist(st["lab"][i], p["_colour"]) > 16 and st["area"][i] > 0.0005 * fig["area"]:
                odd.setdefault(colour_word(st["lab"][i]), []).append(int(i))
        for word, ids in sorted(odd.items(), key=lambda t: -sum(st["area"][i] for i in t[1])):
            share = float(sum(st["area"][i] for i in ids)) / fig["area"]
            if share >= 0.003:
                ids = sorted(ids, key=lambda i: -st["area"][i])
                doubts.append(f"part '{p['name']}' ({colour_word(p['_colour'])}) holds {word} regions "
                              f"{', '.join(map(str, ids[:6]))} ({100 * share:.1f} % of the figure): look at them on "
                              f"the parts sheet; name their material if it is another one")
    doubts += two_colour_regions(reg, L, core, st, parts, fig)
    by_name = {p["name"]: p for p in parts}
    if "hair" in by_name:
        hr = set(by_name["hair"]["regions"])
        for p in parts:
            if p["name"] in ("hair",) or p["kind"] in ("eyes",):
                continue
            touch = sum(c for i in p["regions"] for j, c in nb.get(i, {}).items() if j in hr)
            if touch > 40 * s and cdist(p["_colour"], by_name["hair"]["_colour"]) < 18:
                doubts.append(f"part '{p['name']}' is close to the hair's colour and touches it: no colour tells "
                              "them apart there, so look along that border on the parts sheet and give points on both "
                              "sides of it where it goes wrong")

    # 5. write
    sub_path = Path(a.subject)
    sub_path.parent.mkdir(parents=True, exist_ok=True)
    stem = sub_path.stem
    rp = sub_path.with_name(f"{stem}.regions.png")
    if n > 65535:
        die("more than 65535 regions: the picture is too noisy for automatic parts")
    cv2.imwrite(str(rp), reg.astype(np.uint16))
    try:
        image_rel = os.path.relpath(Path(a.image).resolve(), sub_path.resolve().parent).replace("\\", "/")
    except ValueError:
        image_rel = str(Path(a.image).resolve()).replace("\\", "/")
    fams = {p["name"]: samples(p["regions"], reg) for p in parts}
    out_parts = [{"name": p["name"], "family": p["name"], "kind": p["kind"], "regions": [int(i) for i in p["regions"]]}
                 for p in parts]
    sj = {"format": "refinish-subject/1", "image": image_rel, "upscaled": a.upscaled,
          **({"head_px": a.head_px} if a.head_px else {}),
          "regions": rp.name, "families": fams, "parts": out_parts, "protect": protect, "focal": focal,
          "blush": blush}
    sub_path.write_text(json.dumps(sj, ensure_ascii=False, indent=1), encoding="utf-8")
    rv, fv = sub_path.with_name(f"{stem}.auto.jpg"), sub_path.with_name(f"{stem}.face.jpg")
    review(img, alpha, reg, parts, rv, fv, [p["box"] for p in protect], face["box"] if face is not None else None)
    sv = sub_path.with_name(f"{stem}.sheet.jpg")
    parts_sheet(img, alpha, reg, parts, sv, fig["area"])
    emit({"subject": str(sub_path), "regions": n,
          "parts": [{"name": p["name"], "kind": p["kind"], "colour_lab": [round(float(v), 1) for v in p["_colour"]],
                     "share": round(float(st["area"][p["regions"]].sum() / fig["area"]), 4),
                     **({"why": p["_why"]} if p.get("_why") else {})} for p in parts],
          "protect": protect, "focal": focal, "doubts": doubts, "review": [str(rv), str(fv), str(sv)]})
    sys.exit(1 if doubts else 0)


if __name__ == "__main__":
    main()
