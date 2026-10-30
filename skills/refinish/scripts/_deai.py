"""The de-AI finish: the picture's own colours and drawing kept, the rendering tells of an image model taken out:
the noisy over-rendered micro-detail, the airbrushed gradients, the soft fuzzy lines, colours a little too vivid.
Framed as finishing quality (what a finishing department would clean up), never as hiding where a picture came from.

It needs no parts. It works area by area on the regions the picture's own lines enclose (the region map
scripts/auto_parts.py writes, with no hints needed), and keeps the eyes and the mouth it boxes as drawn:
  - the rendering noise smoothed first by an edge-preserving filter (bilateral, in Lab): colour edges stay;
  - each area's lightness split into its own tones by a k-means per area (all areas at once): a shadow where the
    area's dark side is a real step down and a real share of it, a light where a small bright patch stands apart;
    the tone shapes cleaned the way a painter lassos them; an area whose dark side is a scatter of fine marks (a
    curly lock's strands, a knit) keeps one tone, its marks left as drawn;
  - every pixel pulled toward its area's tone by `flatten`, but only as far as it is near that tone in colour (the
    guard): a thin strand, a stitch or a freckle that no line or area holds is far from its area's tone and stays as
    drawn, so nothing is painted over and no light fringe opens at an edge;
  - the lines: as drawn (light), or a little crisper in a dark shade of their own colour with a closed outline
    (strong);
  - a slight restraint on chroma.
When the eyes were not found (glasses, closed eyes), the face's focal area is flattened only lightly.

Style keys, section `deai`: `flatten` (0..1), `tones` (2: shadow and base; 3: with a light), `step` (the smallest
tone step kept, L), `min_share`, `min_area` (u²), `noise` (the smoothing's colour range, ΔE), `smooth` (u, its
reach), `guard` ([near, far] ΔE: full pull within `near` of the tone, none beyond `far`), `guard_ab` (the same in
hue and chroma, a*b*), `same_ab` (a*b* within which two colours are one material in light and shade), `shape` (u),
`min_island` (u²), `lines` (`drawn` or `crisp`), `line_dark`, `outline` (u, crisp only), `chroma`.

One rule runs through every step: a colour is only ever moved toward a tone of its own material, the same hue and
chroma; lightness is free. Areas fold together, flecks go into their area and pixels are pulled toward their tone
only within one material, so no step can paint one material in another's colour.
"""
import cv2
import numpy as np

import _lines
from _core import clean_shape, ellipse_mask, lab, piece_blur, protect_mask, rgb
from _parts import region_map


def _area_kmeans(v, r, n, k, iters=8):
    """k clusters of the values v per area r (all areas at once): each value's cluster and the centres (n x k)."""
    cnt = np.bincount(r, minlength=n)
    order = np.lexsort((v, r))
    sv, sr = v[order], r[order]
    start = np.searchsorted(sr, np.arange(n))

    def pct(q):
        idx = np.clip(start + (q * np.maximum(cnt - 1, 0)).astype(np.int64), 0, max(0, len(sv) - 1))
        return np.where(cnt > 0, sv[idx], 0.0)

    qs = (0.2, 0.8) if k == 2 else (0.15, 0.5, 0.85)
    C = np.stack([pct(q) for q in qs], 1).astype(np.float64)
    lab_ = np.zeros(len(v), np.int32)
    for _ in range(iters):
        lab_ = np.abs(v[:, None] - C[r]).argmin(1)
        for j in range(k):
            sel = lab_ == j
            s = np.bincount(r[sel], weights=v[sel], minlength=n)
            c = np.bincount(r[sel], minlength=n)
            C[:, j] = np.where(c > 0, s / np.maximum(c, 1), C[:, j])
    return lab_, C, cnt


def same_colour(c1, c2, ab=6.0, dL=30.0):
    """Whether two colours (Lab, ... x 3) are one material in light and shade: the same hue and chroma within `ab`,
    their lightness free within `dL`. A material's shine and shadow differ in lightness; two materials differ in hue
    or chroma (pink hair against a red hoodie: the Lab distance is only 24, the a*b* distance 21)."""
    c1, c2 = np.asarray(c1, np.float64), np.asarray(c2, np.float64)
    return (np.hypot(c1[..., 1] - c2[..., 1], c1[..., 2] - c2[..., 2]) < ab) & (np.abs(c1[..., 0] - c2[..., 0]) < dL)


def merge_small(reg, small_px, Lab, frac=0.0, ab=6.0, rounds=4):
    """Areas folded into a neighbour of their own colour when they are details of it rather than areas of their own:
    an area smaller than small_px (a glint, a stitch the lines enclose), and, with frac > 0, an area under `frac` of
    its neighbour's size (a patch of shine or shade the rendering outlined inside one material). Only ever into a
    neighbour of the same hue and chroma (same_colour): a strand of pink hair the lines cut off over a red hoodie is
    another material, however small, and keeps its own area."""
    out = reg.copy()
    for _ in range(rounds):
        n = int(out.max()) + 1
        flat = out.ravel()
        cnt = np.bincount(flat, minlength=n)
        mean = np.stack([np.bincount(flat, weights=Lab[..., c].ravel(), minlength=n) / np.maximum(cnt, 1)
                         for c in range(3)], 1)
        a = np.concatenate([out[:, :-1].ravel(), out[:-1, :].ravel()])
        b = np.concatenate([out[:, 1:].ravel(), out[1:, :].ravel()])
        diff = (a != b) & (a > 0) & (b > 0)
        a, b = a[diff], b[diff]
        a, b = np.concatenate([a, b]), np.concatenate([b, a])          # both ways round
        key = a.astype(np.int64) * n + b
        uk, kc = np.unique(key, return_counts=True)
        ua, ub = uk // n, uk % n
        # the neighbours a small area may fold into: of its colour; among them, the one with the most shared edge
        ok = same_colour(mean[ua], mean[ub], ab)
        ua, ub, kc = ua[ok], ub[ok], kc[ok]
        if not len(ua):
            break
        order = np.lexsort((cnt[ub], kc, ua))
        last = np.r_[ua[order][1:] != ua[order][:-1], True]
        nb_ = np.zeros(n, np.int64)
        nb_[ua[order][last]] = ub[order][last]
        has = np.zeros(n, bool)
        has[ua[order][last]] = True
        fold = has & (cnt < small_px)
        if frac > 0:
            fold |= has & (cnt < frac * cnt[nb_])
        fold[0] = False
        if not fold.any():
            break
        parent = np.arange(n)
        parent[fold] = nb_[fold]
        parent[parent[fold]] = parent[parent[fold]]                    # no chains within one round
        new = parent[out]
        if np.array_equal(new, out):
            break
        out = new
    return out


def tone_colours(Ls, key, sel, mix_ab=4.0, max_k=4, seed=3):
    """The colour of each selected pixel's tone: the mean Lab of its key (an area's tone), or, where the key's pixels
    spread in hue and chroma beyond `mix_ab` (several colours in one tone), the mean of its own colour's cluster
    within the key (k-means on a*b*, the fewest clusters, up to max_k, whose spread is within mix_ab). Returns the
    model (h x w x 3, the selected pixels filled) and how many keys were split."""
    h, w = key.shape
    rng = np.random.default_rng(seed)
    idx = np.flatnonzero(sel)
    ks = key.ravel()[idx]
    order = np.argsort(ks, kind="stable")
    ks_s = ks[order]
    px = Ls.reshape(-1, 3)[idx[order]].astype(np.float32)
    _, start, counts = np.unique(ks_s, return_index=True, return_counts=True)
    sub = np.zeros(len(ks_s), np.int64)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.2)
    cv2.setRNGSeed(seed)
    split = 0
    for s0, c in zip(start, counts):
        if c < 40:
            continue
        ab = px[s0:s0 + c, 1:3]
        if np.sqrt(((ab - ab.mean(0)) ** 2).sum(1).mean()) <= mix_ab:
            continue
        sample = ab if c <= 20000 else ab[rng.choice(c, 20000, replace=False)]
        lbl = None
        for k in range(2, max_k + 1):
            _, _, cen = cv2.kmeans(np.ascontiguousarray(sample), k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
            d = np.linalg.norm(ab[:, None, :] - cen[None], axis=2)
            lbl = d.argmin(1)
            if np.sqrt((d[np.arange(c), lbl] ** 2).mean()) <= mix_ab:
                break
        sub[s0:s0 + c] = lbl
        split += 1
    g, inv = np.unique(ks_s * 8 + sub, return_inverse=True)
    cnt = np.bincount(inv, minlength=len(g)).astype(np.float64)
    means = np.stack([np.bincount(inv, weights=px[:, ch], minlength=len(g)) / cnt for ch in range(3)], 1)
    model = np.zeros((h * w, 3), np.float32)
    model[idx[order]] = means[inv]
    return model.reshape(h, w, 3), split


def run(subject, style, img, alpha, parts, U, seed=7):
    ds = style.get("deai", {})
    h, w = alpha.shape
    within = alpha > 0.5
    if not subject.get("regions"):
        raise ValueError("the de-AI finish works on a region map: run scripts/auto_parts.py on the picture first "
                         "(no hints are needed)")
    reg0 = region_map(subject, alpha.shape)
    L_line = _lines.find_lines(img, subject.get("upscaled", 1))
    is_line = L_line > 0.3
    Lab = lab(img)
    # ---- the rendering noise smoothed, colour edges kept --------------------------------------------------------------
    Ls = cv2.bilateralFilter(Lab.astype(np.float32), -1, float(ds.get("noise", 5.0)), U.len(ds.get("smooth", 0.8)))
    Ls = np.where(within[..., None], Ls, Lab)
    # the details folded into an area of their own colour round them (small areas, patches of shine or shade inside
    # one material): their drawing is kept or calmed by the guard, never flattened on its own into a blot; an area
    # of another hue or chroma is never folded, however small
    ab_tol = ds.get("same_ab", 6.0)
    reg = merge_small(reg0, U.area(ds.get("detail_area", 60.0)), Ls, ds.get("patch_frac", 0.0), ab_tol)
    n = int(reg.max()) + 1
    core = within & ~is_line & (reg > 0)
    r = reg[core]
    v = Ls[..., 0][core].astype(np.float64)
    # ---- each area's tones -------------------------------------------------------------------------------------------
    tones = int(ds.get("tones", 3))
    cl, C, cnt = _area_kmeans(v, r, n, 2)
    lo = cl == 0
    share_lo = np.bincount(r[lo], minlength=n) / np.maximum(cnt, 1)
    big = cnt >= U.area(ds.get("min_area", 40.0))
    # a shadow is a minority of its area (or about half): when the dark side is most of it, the dark side is the
    # area's base and its bright bits are sheen, not a lit side
    two = (C[:, 1] - C[:, 0] >= ds.get("step", 7.0)) & (share_lo >= ds.get("min_share", 0.08)) & \
          (share_lo <= ds.get("max_share", 0.65)) & big
    t = np.ones(len(v), np.int32)                       # 0 shadow, 1 base, 2 light
    t[lo & two[r]] = 0
    if tones >= 3:
        hl = (v > C[r, 1] + ds.get("light_step", 10.0)) & (t == 1)
        share_hl = np.bincount(r[hl], minlength=n) / np.maximum(cnt, 1)
        has_hl = (share_hl >= 0.01) & (share_hl <= 0.18) & big
        t[hl & has_hl[r]] = 2
    T = np.full((h, w), 1, np.int32)
    T[core] = t
    sm, isl = U.len(ds.get("shape", 0.8)), U.area(ds.get("min_island", 20.0))
    raw_sh = (T == 0) & core
    shadow = (clean_shape(raw_sh, within, sm, isl, isl) > 0.5) & two[reg] & within
    # an area whose dark side was a scatter of fine marks keeps one tone: its marks stay as drawn
    kept = np.bincount(reg[shadow], minlength=n)
    raw = np.bincount(reg[raw_sh], minlength=n)
    scatter = (raw > 0) & (kept < ds.get("coherent", 0.5) * raw)
    # both sides must hold together: a tone whose pixels lie mostly in small pieces (the flecks of a curly lock's
    # rendering, a base broken up between shadows) is a scatter, and the area keeps one tone
    for side in (two[reg] & ~scatter[reg] & core & ~shadow, shadow & ~scatter[reg]):
        n_b, cb, st_b, _ = cv2.connectedComponentsWithStats(side.astype(np.uint8), connectivity=8)
        if n_b <= 1:
            continue
        ys_, xs_ = np.nonzero(side)
        owner = np.zeros(n_b, np.int64)
        owner[cb[ys_, xs_]] = reg[ys_, xs_]
        sizes = st_b[:, cv2.CC_STAT_AREA].astype(np.float64)
        small = sizes < ds.get("speck_size", 3.0) * isl
        small[0] = False
        total = np.bincount(owner[1:], weights=sizes[1:], minlength=n)
        in_small = np.bincount(owner[small], weights=sizes[small], minlength=n)
        scatter |= (total > 0) & (in_small > ds.get("speck_share", 0.3) * total)
    shadow &= ~scatter[reg]
    raw_li = (T == 2) & core
    light = (clean_shape(raw_li, within, sm, isl, isl) > 0.5) & within & ~shadow
    # a light is one or two clean shapes (a band of shine on hair, the glint on a shoe), never a scatter of specks:
    # an area whose light falls apart into many pieces, or loses most of itself to the cleaning, keeps none
    n_c, cc, st_c, _ = cv2.connectedComponentsWithStats(light.astype(np.uint8), connectivity=8)
    pieces = np.zeros(n, np.int64)
    largest = np.zeros(n, np.int64)
    if n_c > 1:
        ys_, xs_ = np.nonzero(light)
        first = np.zeros(n_c, np.int64)
        first[cc[ys_, xs_]] = reg[ys_, xs_]             # each piece's area (any of its pixels)
        pieces = np.bincount(first[1:], minlength=n)
        np.maximum.at(largest, first[1:], st_c[1:, cv2.CC_STAT_AREA])
    kept_li = np.bincount(reg[light], minlength=n)
    raw_l = np.bincount(reg[raw_li], minlength=n)
    # and a light worth keeping has one real shape among its pieces (a band of shine), not only small glints:
    # scattered sparkle is left to the guard, which smooths it into the base
    specks = (pieces > ds.get("light_pieces", 3)) | ((raw_l > 0) & (kept_li < 0.6 * raw_l)) | \
             (largest < U.area(ds.get("light_min", 120.0)))
    light &= ~specks[reg]
    # each tone's colour per area: the mean of its own pixels; a missing tone falls back to the base
    tone_px = np.where(shadow, 0, np.where(light, 2, 1))[core]
    cols = np.full((3, n, 3), np.nan)
    for j in range(3):
        sel = tone_px == j
        c = np.bincount(r[sel], minlength=n)
        for ch in range(3):
            s = np.bincount(r[sel], weights=Ls[..., ch][core][sel].astype(np.float64), minlength=n)
            cols[j, :, ch] = np.where(c > 0, s / np.maximum(c, 1), np.nan)
    allc = np.zeros((n, 3))
    for ch in range(3):
        allc[:, ch] = np.bincount(r, weights=Ls[..., ch][core].astype(np.float64), minlength=n) / np.maximum(cnt, 1)
    cols[1] = np.where(np.isnan(cols[1]), allc, cols[1])
    for j in (0, 2):
        cols[j] = np.where(np.isnan(cols[j]), cols[1], cols[j])
    cols = np.nan_to_num(cols)
    tt = np.where(shadow, 0, np.where(light, 2, 1))
    model = cols[tt, reg].astype(np.float32)
    # an area may hold several colours with no line between them (a print, a camouflage, a trim whose line is faint):
    # within each of its tones the pixels are clustered by hue and chroma, and each takes its own cluster's colour, so
    # two materials in one tone are never averaged into a third colour; the pixels off the paint (the lines) take the
    # colour of the paint nearest them
    sel = core & within
    n_split = 0
    if sel.any():
        model_c, n_split = tone_colours(Ls, reg.astype(np.int64) * 3 + tt, sel, ds.get("mix_ab", 4.0),
                                       ds.get("max_colours", 6), seed=seed)
        fill = within & ~sel
        if fill.any():
            _, near = cv2.distanceTransformWithLabels((~sel).astype(np.uint8), cv2.DIST_L2, 3,
                                                      labelType=cv2.DIST_LABEL_PIXEL)
            ys_, xs_ = np.nonzero(sel)
            lut = np.zeros((int(near.max()) + 1, 3), np.float32)
            lut[near[ys_, xs_]] = model_c[ys_, xs_]
            model_c[fill] = lut[near[fill]]
        model = np.where(within[..., None], model_c, model)
    # on skin the turn into shadow stays soft (a blush, the shade under a fringe): the tones blended at their edges,
    # never across an area's own edge
    skin = None
    if parts is not None:
        ids = [j for j, p in enumerate(subject["parts"], start=1) if p.get("kind") == "skin"]
        if ids:
            skin = np.isin(parts, ids) & within
    if skin is not None and skin.any() and ds.get("skin_soft", 1.2) > 0:
        sig = U.len(ds.get("skin_soft", 1.2))
        soft = piece_blur(model, reg, sig)
        k = cv2.GaussianBlur(skin.astype(np.float32), (0, 0), 1.0)[..., None]
        model = model * (1 - k) + soft * k
    # ---- the pull toward the tones, only as far as a pixel is near its tone (the guard) ------------------------------
    flat = np.full((h, w), float(ds.get("flatten", 0.55)), np.float32)
    eyes = [p for p in subject.get("protect", []) if "eye" in p.get("name", "")]
    if not eyes and subject.get("focal"):
        flat *= 1.0 - 0.6 * np.clip(ellipse_mask(h, w, subject["focal"]), 0, 1)
    # the guard: a pixel is pulled toward its area's tone only as far as it is that tone's material: near in
    # lightness (the `guard` window, ΔE) and near in hue and chroma (the `guard_ab` window, a*b*): a pixel of another
    # material inside the area (a strand of hair over a hoodie that no line cut off) is never painted in its colour
    g0, g1 = ds.get("guard", [10.0, 24.0])
    a0, a1 = ds.get("guard_ab", [ab_tol, 2.2 * ab_tol])
    d = np.linalg.norm(Ls - model, axis=2)
    d_ab = np.hypot(Ls[..., 1] - model[..., 1], Ls[..., 2] - model[..., 2])
    guard = np.clip((g1 - d) / max(1e-3, g1 - g0), 0, 1) * np.clip((a1 - d_ab) / max(1e-3, a1 - a0), 0, 1)
    wgt = (flat * guard * (reg > 0) * within).astype(np.float32)
    out_lab = Ls + wgt[..., None] * (model - Ls)
    dsp = ds.get("despeckle", 0.0)
    if dsp > 0:
        # strong: the small bright flecks an image model scatters over hair and cloth (glitter, not a drawn shine)
        # go into their area's tone; dark details are lines or areas of their own and are not touched
        dev = (out_lab[..., 0] - model[..., 0])
        # inside areas only, away from lines and from the edges between areas: the soft rim of a line or of an
        # area's edge is drawing, not a fleck
        edge = np.zeros((h, w), np.uint8)
        edge[:, 1:] |= (reg[:, 1:] != reg[:, :-1]).astype(np.uint8)
        edge[1:, :] |= (reg[1:, :] != reg[:-1, :]).astype(np.uint8)
        edge |= (L_line > 0.08).astype(np.uint8)
        k_e = 2 * max(1, U.k(2)) + 1
        near_edge = cv2.dilate(edge, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_e, k_e))) > 0
        # a fleck is a lighter dot of the area's own colour (a glint): another hue is another material, never a fleck
        own = same_colour(out_lab, model, ab_tol, 35.0)
        fleck = (dev > ds.get("speck_step", 3.0)) & (dev < 35.0) & own & core & ~near_edge
        n_s, cs, st_s, _ = cv2.connectedComponentsWithStats(fleck.astype(np.uint8), connectivity=8)
        tiny = st_s[:, cv2.CC_STAT_AREA] < U.area(dsp)
        tiny[0] = False
        fl = tiny[cs]
        # the fleck and its soft rim, never past its own area's edge (a rim taken across into the next area would
        # paint that area's edge in this one's tone)
        f_area = cv2.dilate(np.where(fl, reg, 0).astype(np.float32), np.ones((3, 3), np.uint8))
        sp = (fl | (f_area == reg)) & within & ~is_line & (reg > 0)
        out_lab[sp] = model[sp]
    out_lab[..., 1:] *= ds.get("chroma", 1.0)
    out = rgb(out_lab)
    # ---- the lines ----------------------------------------------------------------------------------------------------
    if ds.get("lines", "drawn") == "crisp":
        a = (np.clip(L_line * 1.3, 0, 1) ** 0.8) * within
        lc = Lab.copy()
        lc[..., 0] *= ds.get("line_dark", 0.85)
        lcol = rgb(lc)
        if ds.get("outline", 0) > 0:
            ol = np.clip(_lines.closed_outline(alpha, U.len(ds["outline"]), 3), 0, 1)
            edge_ink = rgb(np.dstack([np.minimum(Lab[..., 0] * 0.45, 22.0), Lab[..., 1] * 0.5, Lab[..., 2] * 0.5]))
            lcol = np.where((ol > a)[..., None], edge_ink, lcol)
            a = np.maximum(a, ol)
        out = out * (1 - a[..., None]) + lcol * a[..., None]
    else:
        a = (np.clip(L_line * 1.15, 0, 1) ** 0.9) * within
        out = out * (1 - a[..., None]) + img * a[..., None]
    # ---- the eyes and the mouth as drawn --------------------------------------------------------------------------------
    prot = protect_mask(subject, h, w, img, skin, parts=parts)
    out = out * (1 - prot[..., None]) + img * prot[..., None]
    return np.clip(out, 0, 1).astype(np.float32), {"areas": int((cnt > 0).sum()), "two_tone": int((two & ~scatter).sum()),
                                                   "tones_split_by_colour": int(n_split),
                                                   "scattered": int(scatter.sum()),
                                                   "pulled": round(float(wgt[within].mean()), 3)}


def check(img, alpha, out, U, upscaled=1, chroma=1.0):
    """H1, the check made for this engine: patches of paint (off the lines and the outline) whose hue or chroma the
    finish moved. The finish only ever changes lightness and the shapes of tones within a material, so a patch whose
    colour moved is a material painted in another's colour (a strand of hair taking a hoodie's red, a sock taking the
    skin's). Returns findings in the checks' own form (scripts/_check.py)."""
    L_line = _lines.find_lines(img, upscaled)
    ol = _lines.closed_outline(alpha, U.len(1.0), 3)
    drawn = cv2.dilate(((L_line > 0.1) | (ol > 0.1)).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    paint = (alpha > 0.5) & ~drawn
    Ls, Lo = lab(img), lab(out)
    # moved: the a*b* displacement beyond what the finish may move a colour within its material (6, and a style's
    # chroma factor on the most saturated colours); measured as a displacement, not a hue angle, which swings wildly
    # on dark, greyish colours for a move no one sees
    # (against the source's colours times the style's own chroma factor: a style that asks for richer or quieter
    # colour moves every colour by design)
    C = np.hypot(Ls[..., 1], Ls[..., 2]) * chroma
    d_ab = np.hypot(Lo[..., 1] - chroma * Ls[..., 1], Lo[..., 2] - chroma * Ls[..., 2])
    moved = paint & (d_ab > np.maximum(8.0, 0.1 * C))
    m = cv2.morphologyEx(moved.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    found = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if a >= U.area(20.0):
            found.append({"id": "H1", "level": "FAIL", "part": "-", "box": [x, y, x + w, y + h], "area": a,
                          "what": "a patch whose hue or chroma moved: one material painted in another's colour "
                                  "(look at it; a missing line between two materials of near colour)"})
    return found
