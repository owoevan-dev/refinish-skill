"""The pixel engine: a sprite made from a finished cel picture the way a pixel artist builds one, not by shrinking.

  - every part keeps a short ramp of its own (2 to 4 tones taken from its flat paint), its tone shapes smoothed at
    the target scale so details smaller than a pixel go (hatching, fine folds) and what stays reads as clusters;
  - each target pixel first takes the part most of its cell belongs to, then that part's tone most of the cell has:
    no averaging, so no muddy in-between colours, and a lock of hair never takes the skin's colour;
  - a small print (a pattern of keyholes, polka dots: parts the subject marks `"print": true` in its rules) becomes
    evenly spaced single marks, not speckle;
  - the silhouette gets a single-pixel outline with its doubled corners rounded off, in one dark ink or selective
    (selout: a darker shade of the colour it borders, deeper on the side away from the light); the boundaries
    between parts get a line in the darker side's shade; the drawn folds only when the sprite is large enough;
  - eyes too small to shrink are set by rule (a row of lash over the iris colour); larger eyes keep their pupil and
    their catch-light;
  - single stray pixels join their neighbours; spurs and crumbs off the silhouette go; no outline where the frame
    cuts the figure; the fills' and the lines' palettes are limited apart; the alpha is hard.

The style's `pixel` section: `height` (the sprite's height in pixels), `outline` (`selout` or `dark`), `colours` (the
palette's size), `folds_from` (the height from which drawn folds are kept). The cel finish under it is the style's
`base` (a bundled style's id or a path).
"""
import cv2
import numpy as np

import _lines
from _core import lab, rgb

INK = np.array([12.0, 5.0, 3.0], np.float32)


# ----------------------------------------------------------------------------------------------------------- helpers

def zhang_suen(m):
    """Thin a small binary mask to single-pixel lines (Zhang & Suen 1984)."""
    img = m.astype(np.uint8).copy()
    while True:
        changed = False
        for step in (0, 1):
            P = np.pad(img, 1)
            p2, p3, p4, p5 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:]
            p6, p7, p8, p9 = P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(n.astype(np.int32) for n in nb)
            seq = nb + [p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32) for i in range(8))
            c = (((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)) if step == 0 else \
                (((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0))
            rem = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if rem.any():
                img[rem] = 0
                changed = True
        if not changed:
            return img.astype(bool)


def l_corners(m):
    """Doubled corners of single-pixel lines: a pixel whose only two neighbours are one vertical and one horizontal
    (they touch each other diagonally, so the line stays connected without it)."""
    P = np.pad(m, 1)
    n, s, w, e = P[:-2, 1:-1], P[2:, 1:-1], P[1:-1, :-2], P[1:-1, 2:]
    nw, ne, sw, se = P[:-2, :-2], P[:-2, 2:], P[2:, :-2], P[2:, 2:]
    cnt8 = sum(x.astype(np.int32) for x in (n, s, w, e, nw, ne, sw, se))
    ortho = (n & e) | (n & w) | (s & e) | (s & w)
    two = (n.astype(np.int32) + s + w + e) == 2
    return m & (cnt8 == 2) & two & ortho


def pixel_perfect(m):
    """Lines one pixel wide with no doubled corners (the "pixel-perfect" line of pixel art)."""
    m = m.copy()
    for _ in range(4):
        cand = l_corners(m)
        if not cand.any():
            break
        for y, x in zip(*np.nonzero(cand)):
            y0, x0 = max(0, y - 1), max(0, x - 1)
            if l_corners(m[y0:y + 2, x0:x + 2])[y - y0, x - x0]:
                m[y, x] = False
    return m


def kmeans(samples, k, seed=3):
    k = max(1, min(k, len(samples)))
    if k == 1:
        return samples.mean(0, keepdims=True).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.2)
    cv2.setRNGSeed(seed)
    _, _, c = cv2.kmeans(samples.astype(np.float32), k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    return c


def shade(c, dL, cool=8.0, chroma=1.12):
    """A darker step of a colour, the way pixel ramps are built: lower, a little richer, its hue turned toward blue."""
    L, a, b = (float(v) for v in c)
    C, h = np.hypot(a, b) * chroma, np.arctan2(b, a)
    dh = (np.radians(-90.0) - h + np.pi) % (2 * np.pi) - np.pi
    h = h + np.sign(dh) * min(abs(dh), np.radians(cool))
    return np.array([max(3.0, L + dL), C * np.cos(h), C * np.sin(h)], np.float32)


def merge_palette(cols, weights, k):
    """Merge the nearest colours (weighted by their counts) until k are left; returns them and old -> new."""
    cols = [np.array(c, np.float32) for c in cols]
    wts = [float(v) for v in weights]
    groups = [[i] for i in range(len(cols))]
    while len(cols) > k:
        C = np.array(cols)
        d = np.linalg.norm(C[:, None] - C[None], axis=2)
        np.fill_diagonal(d, np.inf)
        i, j = np.unravel_index(np.argmin(d), d.shape)
        i, j = min(i, j), max(i, j)
        cols[i] = (cols[i] * wts[i] + cols[j] * wts[j]) / max(1e-6, wts[i] + wts[j])
        wts[i] += wts[j]
        groups[i] += groups[j]
        del cols[j], wts[j], groups[j]
    mapping = {i: gi for gi, g in enumerate(groups) for i in g}
    return np.array(cols, np.float32), mapping


def part_ramp(Lab, m, max_tones=4, min_share=0.02, merge_de=7.0):
    """A part's own tones: k-means on its flat paint, near ones merged, slivers dropped; dark to light."""
    pts = Lab[m]
    if len(pts) > 60000:
        pts = pts[np.random.default_rng(2).choice(len(pts), 60000, replace=False)]
    c = kmeans(pts, max_tones)
    while True:
        d = np.linalg.norm(pts[:, None] - c[None], axis=2).argmin(1)
        share = np.bincount(d, minlength=len(c)) / len(d)
        c = c[share >= min_share]
        if len(c) <= 1:
            break
        D = np.linalg.norm(c[:, None] - c[None], axis=2)
        np.fill_diagonal(D, np.inf)
        if D.min() >= merge_de:
            break
        i, j = np.unravel_index(np.argmin(D), D.shape)
        c = np.delete(np.vstack([c, (c[i] + c[j]) / 2]), [i, j], axis=0)
    return c[np.argsort(c[:, 0])]


# ------------------------------------------------------------------------------------------------------------- main

def pixelize(img, alpha, parts, subject, height, outline="selout", colours=32, folds_from=128):
    """The sprite (RGBA float, `height` pixels tall, hard alpha) and its palette (RGB, one row) from a finished cel
    picture, its part map and its subject."""
    plist = subject["parts"]
    names = [p["name"] for p in plist]
    kinds = {i + 1: p.get("kind", "cloth") for i, p in enumerate(plist)}
    rules = subject.get("rules", {})
    prints = [n for n in names if rules.get(n, {}).get("print")]
    ys, xs = np.nonzero(alpha > 0.5)
    if not len(ys):
        raise ValueError("the picture has no figure (its alpha is empty)")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    # where the picture's frame cuts the figure off (a bust's chest): no outline along that side
    Hf, Wf = alpha.shape
    op = alpha > 0.5
    cut = {"top": op[0].sum() > 0.05 * Wf, "bottom": op[-1].sum() > 0.05 * Wf,
           "left": op[:, 0].sum() > 0.05 * Hf, "right": op[:, -1].sum() > 0.05 * Hf}
    img, alpha, parts = img[y0:y1, x0:x1], alpha[y0:y1, x0:x1], parts[y0:y1, x0:x1].astype(np.int32)
    H0, W0 = alpha.shape
    s = height / H0
    h, w = height, int(np.ceil(W0 * s))
    yy, xx = np.mgrid[0:H0, 0:W0]
    cell = (np.minimum((yy * s).astype(np.int32), h - 1) * w + np.minimum((xx * s).astype(np.int32), w - 1))
    within = alpha > 0.5
    L_line = _lines.find_lines(img, subject.get("upscaled", 1))
    is_line = (L_line > 0.3) & within
    Lab = lab(img)
    cellpx = 1.0 / s
    print_ids = {names.index(n) + 1 for n in prints}
    # ---- every part's ramp, its tone shapes smoothed at the target scale -------------------------------------------
    ramps, tone = {}, np.full(alpha.shape, -1, np.int32)
    for j in np.unique(parts[within]):
        m = (parts == j) & within
        if j == 0 or j in print_ids or m.sum() < 20:
            continue
        paint = m & ~is_line
        if paint.sum() < 20:
            paint = m
        c = part_ramp(Lab, paint)
        ramps[j] = c
        if len(c) == 1:
            tone[m] = 0
            continue
        t = np.linalg.norm(Lab[..., None, :] - c[None, None], axis=3).argmin(2)
        sig = max(0.6, 0.45 * cellpx)
        score = np.stack([cv2.GaussianBlur(((t == k) & paint).astype(np.float32), (0, 0), sig) for k in range(len(c))])
        tone[m] = score.argmax(0)[m]
    # prints sit on the part under them for the paint: their pixels go to the nearest other part
    if print_ids:
        pm = np.isin(parts, list(print_ids)) & within
        other = within & ~pm
        _, near = cv2.distanceTransformWithLabels((~other).astype(np.uint8), cv2.DIST_L2, 3,
                                                  labelType=cv2.DIST_LABEL_PIXEL)
        oys, oxs = np.nonzero(other)
        lut_p = np.zeros(near.max() + 1, np.int32)
        lut_t = np.zeros(near.max() + 1, np.int32)
        lut_p[near[oys, oxs]] = parts[oys, oxs]
        lut_t[near[oys, oxs]] = tone[oys, oxs]
        parts_paint = parts.copy()
        parts_paint[pm] = lut_p[near[pm]]
        tone[pm] = lut_t[near[pm]]
    else:
        parts_paint = parts
    # ---- vote: the part, then its tone ------------------------------------------------------------------------------
    cov = np.bincount(cell.ravel(), weights=alpha.ravel(), minlength=h * w).reshape(h, w)
    area = np.bincount(cell.ravel(), minlength=h * w).reshape(h, w)
    solid = cov / np.maximum(area, 1) > 0.5
    P = int(parts.max()) + 1
    v = within.ravel()
    pc = np.bincount(cell.ravel()[v] * P + parts_paint.ravel()[v], minlength=h * w * P).reshape(h * w, P)
    pc[:, 0] = 0
    part_lr = pc.argmax(1).reshape(h, w)
    T = 4
    ok = v & (tone.ravel() >= 0)
    key = (cell.ravel()[ok] * P + parts_paint.ravel()[ok]) * T + tone.ravel()[ok]
    tc = np.bincount(key, minlength=h * w * P * T).reshape(h * w, P, T)
    tone_lr = tc[np.arange(h * w), part_lr.ravel()].argmax(1).reshape(h, w)
    col = np.zeros((h, w, 3), np.float32)
    for j, c in ramps.items():
        sel = solid & (part_lr == j)
        col[sel] = c[np.minimum(tone_lr[sel], len(c) - 1)]
    # ---- prints: evenly spaced single marks -------------------------------------------------------------------------
    marks = np.zeros((h, w), bool)
    for j in print_ids:
        pm8 = ((parts == j) & within).astype(np.uint8)
        _, _, st, cen = cv2.connectedComponentsWithStats(pm8)
        pcol = np.median(Lab[pm8 > 0], axis=0) if pm8.any() else INK
        for i in np.argsort(-st[1:, cv2.CC_STAT_AREA]) + 1:
            if st[i, cv2.CC_STAT_AREA] < 0.15 * cellpx * cellpx:
                continue
            mx, my = int(cen[i][0] * s), int(cen[i][1] * s)
            if not (0 <= my < h and 0 <= mx < w) or not solid[my, mx]:
                continue
            gap = 1 if height >= 90 else 2                         # a print sparser on a small sprite
            if marks[max(0, my - gap):my + gap + 1, max(0, mx - gap):mx + gap + 1].any():
                continue
            marks[my, mx] = True
            col[my, mx] = pcol
            if st[i, cv2.CC_STAT_HEIGHT] * s >= 1.6 and my + 1 < h and solid[my + 1, mx]:
                marks[my + 1, mx] = True
                col[my + 1, mx] = pcol
    # ---- the silhouette cleared of spurs and crumbs ------------------------------------------------------------------
    hair_ids = [j for j, k in kinds.items() if k == "hair"]
    for _ in range(2):
        # a spur sticks out into the background: transparent on both sides of it (left and right, or above and
        # below); a narrow face between a hand and the hair is not one
        Pq = np.pad(solid, 1)
        n_, s_, w_, e_ = Pq[:-2, 1:-1], Pq[2:, 1:-1], Pq[1:-1, :-2], Pq[1:-1, 2:]
        thin = (solid & ((~n_ & ~s_) | (~w_ & ~e_))).astype(np.uint8)
        n, lb, st, _ = cv2.connectedComponentsWithStats(thin, connectivity=8)
        for i in range(1, n):
            comp = lb == i
            limit = 8 if np.isin(part_lr[comp], hair_ids).mean() > 0.5 else 2
            if st[i, cv2.CC_STAT_AREA] <= limit:
                solid &= ~comp
        n, lb, st, _ = cv2.connectedComponentsWithStats(solid.astype(np.uint8), connectivity=8)
        if n > 2:
            big = st[1:, cv2.CC_STAT_AREA].argmax() + 1
            for i in range(1, n):
                if i != big and st[i, cv2.CC_STAT_AREA] <= 4:
                    solid &= lb != i
        col[~solid] = 0
    # ---- lines --------------------------------------------------------------------------------------------------------
    Ps = np.pad(solid, 1)
    if cut["top"]:
        Ps[0, 1:-1] = solid[0]
    if cut["bottom"]:
        Ps[-1, 1:-1] = solid[-1]
    if cut["left"]:
        Ps[1:-1, 0] = solid[:, 0]
    if cut["right"]:
        Ps[1:-1, -1] = solid[:, -1]
    edge = solid & ~(Ps[:-2, 1:-1] & Ps[2:, 1:-1] & Ps[1:-1, :-2] & Ps[1:-1, 2:])
    lit_side = solid & ~(Ps[:-2, 1:-1] & Ps[1:-1, :-2])
    rounded = edge & l_corners(edge)
    solid &= ~rounded
    edge &= ~rounded
    major = {j for j, k in kinds.items() if k not in ("eyes", "accessory")} - print_ids
    bound = np.zeros((h, w), bool)
    Lmap = col[..., 0]
    Pp = np.pad(part_lr, 1, constant_values=-1)
    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        nb = Pp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
        nbL = np.pad(Lmap, 1)[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
        diff = solid & (nb > 0) & (nb != part_lr) & np.isin(part_lr, list(major)) & np.isin(nb, list(major))
        bound |= diff & (Lmap < nbL)                              # the line on the darker side
    # the drawn lines that still read at this size: heavy ones always (a hand's contour against the face), the folds
    # only on larger sprites
    lcov = np.bincount(cell.ravel(), weights=is_line.ravel().astype(np.float64), minlength=h * w).reshape(h, w)
    thr = 0.2 if height >= folds_from else (0.26 if height >= 90 else 0.32)
    drawn = zhang_suen((lcov / np.maximum(area, 1) > thr) & solid)
    n, lb, st, _ = cv2.connectedComponentsWithStats(drawn.astype(np.uint8), connectivity=8)
    long_ = np.zeros(n, bool)
    span = np.maximum(st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT])
    for i in range(1, n):
        in_hair = np.isin(part_lr[lb == i], hair_ids).mean() > 0.5
        # the hair's strand lines thin out to the few long ones: drawn densely they read as stripes
        need = (6 if height >= folds_from else 8) if in_hair else (5 if height >= folds_from else 4)
        long_[i] = span[i] >= need
    bound |= long_[lb] & drawn
    inner = pixel_perfect(zhang_suen(bound) & ~edge) & solid & ~marks
    # ---- the fills' own palette first, so a line's shade never merges back into the colour it borders -------------------
    key = np.round(col * 2).astype(np.int32)
    res = col.copy()
    for yv, xv in zip(*np.nonzero(solid & ~marks)):
        nbs = [(a_, b_) for a_ in (yv - 1, yv, yv + 1) for b_ in (xv - 1, xv, xv + 1)
               if (a_, b_) != (yv, xv) and 0 <= a_ < h and 0 <= b_ < w and solid[a_, b_] and not marks[a_, b_]]
        if len(nbs) >= 3 and not any((key[a_, b_] == key[yv, xv]).all() for a_, b_ in nbs):
            vals, cnts = np.unique(np.array([key[a_, b_] for a_, b_ in nbs]), axis=0, return_counts=True)
            res[yv, xv] = vals[cnts.argmax()] / 2.0
    col = res
    uniq, inv, cnt = np.unique(np.round(col[solid], 1), axis=0, return_inverse=True, return_counts=True)
    n_line = max(4, colours // 4)
    pal_f, mapping = merge_palette(uniq, cnt, colours - n_line)
    col[solid] = pal_f[np.array([mapping[i] for i in np.asarray(inv).ravel()])]
    out = col.copy()
    if outline == "dark":
        out[edge] = INK
        for yv, xv in zip(*np.nonzero(inner)):
            out[yv, xv] = shade(col[yv, xv], -30.0)
    else:
        for yv, xv in zip(*np.nonzero(edge)):
            out[yv, xv] = shade(col[yv, xv], -24.0) if lit_side[yv, xv] else shade(col[yv, xv], -48.0, cool=14.0)
        for yv, xv in zip(*np.nonzero(inner)):
            out[yv, xv] = shade(col[yv, xv], -26.0)
    # ---- eyes -----------------------------------------------------------------------------------------------------------
    fixed_px = edge | inner | marks
    for p in subject.get("protect", []):
        if "eye" not in p.get("name", ""):
            continue
        bx0, by0, bx1, by1 = p["box"]
        X0, X1, Y0, Y1 = (bx0 - x0) * s, (bx1 - x0) * s, (by0 - y0) * s, (by1 - y0) * s
        box = (slice(max(0, by0 - y0), max(0, by1 - y0)), slice(max(0, bx0 - x0), max(0, bx1 - x0)))
        sub = Lab[box]
        if sub.size == 0:
            continue
        flat = sub.reshape(-1, 3)
        iris = np.median(flat[(flat[:, 0] < np.percentile(flat[:, 0], 45)) & (flat[:, 0] > 8)], axis=0) \
            if (flat[:, 0] > 8).any() else np.array([25.0, 5, 0], np.float32)
        ex, ey = int((X0 + X1) / 2), int((Y0 + Y1) / 2)
        if not (0 <= ey < h and 0 <= ex < w):
            continue
        if Y1 - Y0 < 4:
            # a small eye by rule: a row of lash over the iris colour; a darker pupil when it is two pixels wide, a
            # catch-light when it is three tall. Sized from the eye's own dark marks (lashes, iris), not the padded
            # box round it, and never wider than two pixels: a pixel artist's eye at this size is one or two pixels,
            # dark; three wide in a saturated iris colour it reads as goggles
            dark = sub[..., 0] < np.percentile(sub[..., 0], 60) - 18
            if dark.sum() >= 4:
                ys_, xs_ = np.nonzero(dark)
                dX0, dX1 = (xs_.min() + box[1].start) * s, (xs_.max() + 1 + box[1].start) * s
                dY0, dY1 = (ys_.min() + box[0].start) * s, (ys_.max() + 1 + box[0].start) * s
            else:
                dX0, dX1, dY0, dY1 = X0, X1, Y0, Y1
            ew = int(np.clip(round(dX1 - dX0), 1, 2))
            eh = int(np.clip(round(dY1 - dY0), 2, 3))
            ex0 = int(round((dX0 + dX1) / 2 - ew / 2))
            ey0 = int(round(dY0))
            iris_c = shade(iris, -14.0, cool=0.0, chroma=1.0)
            # the eye's own parts (its white, its iris) cover more of the box than an eye this size can: they take
            # the face's skin first, and the eye is drawn over it
            eye_ids = [j for j, k in kinds.items() if k == "eyes"]
            skin_ids = [j for j, k in kinds.items() if k == "skin"]
            if eye_ids and skin_ids:
                ya, yb = max(0, int(np.floor(Y0))), min(h, int(np.ceil(Y1)) + 1)
                xa, xb = max(0, int(np.floor(X0))), min(w, int(np.ceil(X1)) + 1)
                is_eye = np.zeros((h, w), bool)
                is_eye[ya:yb, xa:xb] = np.isin(part_lr[ya:yb, xa:xb], eye_ids) & solid[ya:yb, xa:xb]
                near = np.zeros((h, w), bool)
                near[max(0, ya - 3):min(h, yb + 3), max(0, xa - 3):min(w, xb + 3)] = True
                skin_near = near & np.isin(part_lr, skin_ids) & solid & ~fixed_px
                if is_eye.any() and skin_near.any():
                    out[is_eye] = np.median(out[skin_near], axis=0)
            for dy in range(eh):
                for dx in range(ew):
                    yv, xv = ey0 + dy, ex0 + dx
                    if not (0 <= yv < h and 0 <= xv < w and solid[yv, xv]):
                        continue
                    out[yv, xv] = INK if dy == 0 else (shade(iris_c, -10.0) if (ew >= 2 and dx == ew // 2 and
                                                                                dy == eh - 1) else iris_c)
                    fixed_px[yv, xv] = True
            if ew >= 2 and eh >= 3 and 0 <= ey0 + 1 < h and 0 <= ex0 < w:
                out[ey0 + 1, ex0] = np.array([96.0, 0, 0], np.float32)
            # an eye this small stays readable only against skin: the face's commonest skin colour beside it and
            # under it, over the fringe's colour and the shade under it (a red fringe and a red-brown shade round a red
            # iris read as goggles); the pixels above it are the fringe's, and the silhouette's outline is kept
            if skin_ids:
                face_win = np.zeros((h, w), bool)
                face_win[max(0, ey0 - 4):min(h, ey0 + eh + 4), max(0, ex0 - 5):min(w, ex0 + ew + 5)] = True
                skin_px = face_win & np.isin(part_lr, skin_ids) & solid & ~fixed_px
                if skin_px.any():
                    vals, counts = np.unique(np.round(out[skin_px], 1), axis=0, return_counts=True)
                    skin_base = vals[counts.argmax()].astype(np.float32)
                    ring = [(ey0 + dy, ex0 - 1) for dy in range(eh)] + [(ey0 + dy, ex0 + ew) for dy in range(eh)]
                    ring += [(ey0 + eh, ex0 + dx) for dx in range(ew)]
                    for yv, xv in ring:
                        if 0 <= yv < h and 0 <= xv < w and solid[yv, xv] and not edge[yv, xv] \
                                and not (fixed_px[yv, xv] and not inner[yv, xv]):
                            out[yv, xv] = skin_base
        else:
            # big enough to shrink: keep its pupil dark and its catch-light white
            Lb = sub[..., 0]
            py, px = np.unravel_index(np.argmin(np.where(Lb > 3, Lb, 99)), Lb.shape)
            hy, hx = np.unravel_index(np.argmax(Lb * (sub[..., 1] ** 2 + sub[..., 2] ** 2 < 60)), Lb.shape)
            for (yy_, xx_, c_) in ((py, px, INK), (hy, hx, np.array([97.0, 0, 0], np.float32))):
                Y_, X_ = int((yy_ + box[0].start) * s), int((xx_ + box[1].start) * s)
                if 0 <= Y_ < h and 0 <= X_ < w:
                    out[Y_, X_] = c_
                    fixed_px[Y_, X_] = True
    # ---- the lines' and the eyes' colours limited among themselves, then the whole palette ------------------------------
    line_px = solid & (edge | inner | (fixed_px & ~marks))
    final = out.copy()
    if line_px.any():
        uniq, inv, cnt = np.unique(np.round(out[line_px], 1), axis=0, return_inverse=True, return_counts=True)
        pal_l, mapping = merge_palette(uniq, cnt, n_line)
        final[line_px] = pal_l[np.array([mapping[i] for i in np.asarray(inv).ravel()])]
    pal = np.unique(np.round(final[solid], 3), axis=0)
    final[~solid] = 0
    return np.dstack([rgb(final), solid.astype(np.float32)]), rgb(pal.reshape(1, -1, 3))[0]
