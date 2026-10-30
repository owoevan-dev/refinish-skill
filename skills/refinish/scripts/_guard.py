"""The same-material guard: pixels a part map put in the wrong part, given back to the part whose material they are.

A part map drawn by hand or found by scripts/auto_parts.py is never exact: a pink strand of hair crossing a red hoodie
lands in the hoodie, a button in the cloth round it. A cel finish paints every pixel of a part from that part's colour
model, so such a strand would turn red. Before painting, each part's material is read as the few colours most of its
pixels have, away from its borders (a*b* as they are, lightness weighted down: one material in light and in shadow);
a run of pixels far from all of them that matches a neighbouring part's material and touches that part (across a line
at most) is moved to that part; a large run moves there even without touching it (a forearm cut off from the skin by
a rolled sleeve). A run farther still that matches no neighbour (the dark inside of a coat labelled skin, a clip, a
badge) is kept as drawn instead of painted in a colour that is not its own: by default only inside the skin, whose
own colours lie close together; with `"keep_strays": true` in every painted part, though a part's own highlights (the
light on dark hair, the gloss on a shoe) lie as far from its material and would then keep their soft rendering.
"""
import cv2
import numpy as np

from _core import lab


def dark_lines(img, within, U, depth=12.0, reach=1.5):
    """A quick stand-in for the line art: pixels at least `depth` darker (L) than the lightest of their surroundings
    within `reach` u (a black-hat). Enough to keep lines out of a part's material colours and to bridge them."""
    L = lab(img)[..., 0]
    r = max(1, int(round(U.len(reach))))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, k)
    return (bh > depth) & within


KEPT = "kept-as-drawn"


def guard_parts(sj, style, img, alpha, parts, U, rule=None):
    """The guard as refinish.py runs it before any engine that paints by parts. Off with `"guard": {"on": false}` in
    the style; its thresholds (`out_ab`, `in_ab`, `margin`, `min_area` u², `far_area` u², `far_kinds`, `bridge` u)
    there too.
    `keep_strays` ("skin" by default, true for every painted part, false for none; with `keep_ab`, `keep_area` u²): the
    runs kept as drawn become one more part, `kept-as-drawn`, whose rule is `"model": "keep"`. Returns (subject, parts,
    info)."""
    cfg = dict(style.get("guard", {}))
    if not cfg.pop("on", True):
        return sj, parts, {}
    keep = cfg.pop("keep_strays", "skin")
    within = alpha > 0.5
    is_line = dark_lines(img, within, U)
    plist = sj["parts"]
    painted = [j for j, p in enumerate(plist, start=1)
               if rule is None or rule(style, sj, p).get("model", "part") != "keep"]
    keep_in = (set(painted) if keep is True else
               {j for j, p in enumerate(plist, start=1) if p.get("kind", p.get("as")) == "skin"} if keep == "skin"
               else set())
    far_to = {j for j, p in enumerate(plist, start=1) if p.get("kind", p.get("as")) in cfg.pop("far_kinds", ("skin", "hair"))}
    new, moved, log, kept = material_guard(img, parts, within, is_line, U, painted,
                                           keep_id=len(plist) + 1 if keep_in else None, keep_in=keep_in, far_to=far_to,
                                           **cfg)
    names = {j: p["name"] for j, p in enumerate(plist, start=1)}
    if kept:
        sj = dict(sj)
        sj["parts"] = list(plist) + [{"name": KEPT, "kind": "accessory"}]
        sj["rules"] = {**sj.get("rules", {}), KEPT: {"model": "keep"}}
        names[len(plist) + 1] = KEPT
    if not (moved or kept):
        return sj, new, {}
    return sj, new, {"guard": {"moved_px": moved, "kept_px": kept,
                               "moves": [{"from": names.get(m["from"]), "to": names.get(m["to"]), "px": m["px"]}
                                         for m in log]}}


def materials(ab, k_max=3, min_share=0.12, seed=3):
    """A part's material colours: k-means on its colours (L scaled by L_W, a*b* as they are), the clusters holding at
    least `min_share` of it."""
    n = len(ab)
    if n < 30:
        return np.median(ab, axis=0, keepdims=True) if n else np.zeros((0, ab.shape[1]), np.float32)
    rng = np.random.default_rng(seed)
    sample = ab[rng.choice(n, min(n, 20000), replace=False)].astype(np.float32)
    k = min(k_max, max(1, len(sample) // 50))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.2)
    cv2.setRNGSeed(seed)
    _, lbl, cen = cv2.kmeans(sample, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=k) / len(sample)
    keep = cen[share >= min_share]
    return keep if len(keep) else cen[[int(np.argmax(share))]]


L_W = 0.3


def _dist(ab, cols):
    """Each pixel's a*b* distance to the nearest of `cols`."""
    if len(cols) == 0:
        return np.full(len(ab), np.inf, np.float32)
    cols = np.asarray(cols, np.float32).reshape(-1, ab.shape[1])
    d = np.linalg.norm(ab[:, None, :] - cols[None, :, :], axis=2)
    return d.min(axis=1)


def material_guard(img, parts, within, is_line, U, painted, out_ab=12.0, in_ab=7.0, margin=5.0, min_area=2.0,
                   bridge=1.2, keep_ab=18.0, keep_area=6.0, keep_id=None, far_area=40.0, keep_in=None, far_to=None):
    """The part map with stray pixels moved to the part whose material they are. `painted`: the part ids a colour model
    paints (only their strays matter; any part may receive). A run that reaches no pixel of the part whose material it is
    moves there only when it is at least `far_area` u². Runs of at least `keep_area` u² farther than `keep_ab` from
    their part's material that match no neighbour go to `keep_id` (kept as drawn) when it is given. Returns (new parts,
    moved pixel count, per-part moves, kept pixel count)."""
    f = lab(img)
    # lightness counts a little: a material's light and shadow lie 15 to 30 apart in L, but navy hair and a lilac
    # cardigan, a black coat and a white shirt, have nearly the same a*b* and lie 40 to 60 apart
    ab = np.dstack([f[..., 0] * L_W, f[..., 1], f[..., 2]])
    core = within & ~is_line
    ids = [int(j) for j in np.unique(parts[within]) if j > 0]
    # a part's material read away from its borders, where a map's mistakes lie: the pixels at least 3 u inside it
    # (the whole part when too little of it is that far in)
    mats = {}
    for j in ids:
        mj = (parts == j)
        inner = core & mj & (cv2.distanceTransform(mj.astype(np.uint8), cv2.DIST_L2, 5) > U.len(3.0))
        whole = core & mj
        mats[j] = materials(ab[inner] if inner.sum() >= max(500, 0.3 * whole.sum()) else ab[whole])
    new = parts.copy()
    moved, log, kept = 0, [], 0
    r = max(1, int(round(U.len(bridge))))
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    for j in painted:
        m = core & (parts == j)
        if m.sum() < 50:
            continue
        ys, xs = np.nonzero(m)
        d_own = _dist(ab[ys, xs], mats[j])
        out = d_own > out_ab
        if out.sum() < U.area(min_area):
            continue
        oy, ox = ys[out], xs[out]
        stray = np.zeros(parts.shape, bool)
        stray[oy, ox] = True
        # the region round the strays, where a neighbour must lie
        y0, y1 = max(0, oy.min() - 4 * r), min(parts.shape[0], oy.max() + 4 * r + 1)
        x0, x1 = max(0, ox.min() - 4 * r), min(parts.shape[1], ox.max() + 4 * r + 1)
        win = (slice(y0, y1), slice(x0, x1))
        best_d = np.full(len(oy), np.inf, np.float32)
        best_k = np.zeros(len(oy), np.int32)
        for k in ids:
            if k == j or len(mats[k]) == 0:
                continue
            km = (new[win] == k) & within[win]
            if not km.any():
                continue
            dk = _dist(ab[oy, ox], mats[k])
            ok = (dk < in_ab) & (dk < d_own[out] - margin)
            if not ok.any():
                continue
            # the strays of k's colour that reach k's own pixels, across a line at most
            cand = np.zeros(parts.shape, np.uint8)
            cand[oy[ok], ox[ok]] = 1
            c_w = cand[win]
            joined = cv2.dilate(c_w, kern) | km.astype(np.uint8)
            n, cc = cv2.connectedComponents(joined, connectivity=8)
            touching = np.zeros(n, bool)
            touching[np.unique(cc[km])] = True
            touching[0] = False
            reach = touching[cc] & (c_w > 0)
            sel = reach[oy[ok] - y0, ox[ok] - x0]
            idx = np.nonzero(ok)[0][sel]
            better = dk[idx] < best_d[idx]
            best_d[idx[better]] = dk[idx[better]]
            best_k[idx[better]] = k
        # a large run of another part's material that reaches none of its pixels (a forearm cut off from the skin by a
        # rolled sleeve, labelled as the sleeve): its colour alone says what it is, when the run is big enough that it
        # is a piece of a part and not a print
        far = (best_k == 0) & (d_own[out] > out_ab)
        if far.sum() >= U.area(far_area):
            fd = np.full(len(oy), np.inf, np.float32)
            fk = np.zeros(len(oy), np.int32)
            for k in ids:
                # only into a major material a map often cuts off (the skin of an arm, a lock of hair), never into a
                # small family (a draft's patch of a face's shade would take a knee's flush)
                if k == j or len(mats[k]) == 0 or (far_to is not None and k not in far_to):
                    continue
                dk = _dist(ab[oy, ox], mats[k])
                ok = far & (dk < in_ab) & (dk < d_own[out] - margin) & (dk < fd)
                fd[ok], fk[ok] = dk[ok], k
            cand = fk > 0
            if cand.any():
                mv = np.zeros(parts.shape, np.uint8)
                mv[oy[cand], ox[cand]] = 1
                n, cc, st, _ = cv2.connectedComponentsWithStats(cv2.morphologyEx(mv, cv2.MORPH_CLOSE, kern), connectivity=8)
                big = np.zeros(n, bool)
                big[1:] = st[1:, cv2.CC_STAT_AREA] >= U.area(far_area)
                keep_far = cand & big[cc[oy, ox]]
                # and only a run much smaller than the part it joins: a piece of it, not a second one
                if keep_far.any():
                    size = np.bincount(cc[oy, ox][keep_far], minlength=n)
                    area_k = {k: int((parts == k).sum()) for k in np.unique(fk[keep_far])}
                    small = np.array([size[c_] * 2 <= area_k[k_] for c_, k_ in zip(cc[oy, ox][keep_far],
                                                                                fk[keep_far])], bool)
                    idx = np.nonzero(keep_far)[0][small]
                    best_k[idx] = fk[idx]
        hit = best_k > 0
        if hit.any():
            # runs too small to be a strand or a button are left (flecks of noise)
            mv = np.zeros(parts.shape, np.uint8)
            mv[oy[hit], ox[hit]] = 1
            n, cc, st, _ = cv2.connectedComponentsWithStats(mv, connectivity=8)
            big = np.zeros(n, bool)
            big[1:] = st[1:, cv2.CC_STAT_AREA] >= U.area(min_area)
            sel = big[cc[oy[hit], ox[hit]]]
            hy, hx, hk = oy[hit][sel], ox[hit][sel], best_k[hit][sel]
            new[hy, hx] = hk
            moved += len(hy)
            for k in np.unique(hk):
                log.append({"from": j, "to": int(k), "px": int((hk == k).sum())})
        rest = ~hit & (d_own[out] > keep_ab)
        if keep_id is not None and (keep_in is None or j in keep_in) and rest.sum() >= U.area(keep_area):
            # far from its part and from every neighbour: its own material, kept as drawn
            kp = np.zeros(parts.shape, np.uint8)
            kp[oy[rest], ox[rest]] = 1
            kp = cv2.morphologyEx(kp, cv2.MORPH_CLOSE, kern)
            n, cc, st, _ = cv2.connectedComponentsWithStats(kp, connectivity=8)
            big = np.zeros(n, bool)
            big[1:] = st[1:, cv2.CC_STAT_AREA] >= U.area(keep_area)
            sel = big[cc] & (kp > 0) & m
            new[sel] = keep_id
            kept += int(sel.sum())
    if moved or kept:
        # the lines inside a moved run go with it: a line pixel next to moved pixels takes the part they moved to
        changed = (new != parts) & core
        fix = is_line & within & (cv2.dilate(changed.astype(np.uint8), kern) > 0)
        if fix.any():
            moved_to = np.where(changed, new, 0).astype(np.uint16)
            spread = cv2.dilate(moved_to, kern)          # the largest id among the moved neighbours
            new[fix & (spread > 0)] = spread[fix & (spread > 0)]
    return new, moved, log, kept
