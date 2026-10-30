"""The flat tones of a cel finish, read back per part: which tone of its part each pixel was painted in (shadow,
base, light), and the colour of each tone. The print and drawing engines build on these instead of on raw pixels:
a woodblock's colour blocks, a watercolour's glazes, a pencil's shadow boundaries."""
import cv2
import numpy as np

from _core import lab


def part_tones(Lv, m, k=3, min_share=0.03, merge_L=6.0):
    """A part's flat tones (their lightness, dark to light) and each of its pixels' tone index (in m's order)."""
    v = Lv[m]
    if len(v) < 30:
        return np.array([float(np.median(v)) if len(v) else 50.0]), np.zeros(int(m.sum()), np.int32)
    qs = np.percentile(v, np.linspace(100.0 / (2 * k), 100 - 100.0 / (2 * k), k))
    c = np.array(sorted(set(np.round(qs, 1))), np.float64)
    for _ in range(25):
        idx = np.abs(v[:, None] - c[None]).argmin(1)
        new = np.array([v[idx == i].mean() if (idx == i).any() else c[i] for i in range(len(c))])
        if np.allclose(new, c, atol=0.05):
            break
        c = new
    idx = np.abs(v[:, None] - c[None]).argmin(1)
    c = c[[i for i in range(len(c)) if (idx == i).mean() >= min_share]]
    merged = [c[0]]
    for x in c[1:]:
        if x - merged[-1] < merge_L:
            merged[-1] = (merged[-1] + x) / 2
        else:
            merged.append(x)
    c = np.array(merged)
    return c, np.abs(v[:, None] - c[None]).argmin(1).astype(np.int32)


def colour_pieces(L, m, k_max=8, spread=6.0, min_share=0.03, seed=3):
    """A part of several colours (an accessory: a basket of vegetables, a badge) split into the pieces of each colour:
    a k-means of its pixels' colours (lightness counting half, so one colour in light and shade stays one piece), the
    clusters holding at least `min_share` of it; a part of one colour (its a*b* spread under `spread`) stays whole."""
    px = L[m]
    if len(px) < 200 or float(np.std(px[:, 1:], axis=0).max()) < spread:
        return [m]
    feat = np.stack([px[:, 0] * 0.5, px[:, 1], px[:, 2]], 1).astype(np.float32)
    rng = np.random.default_rng(seed)
    sample = feat[rng.choice(len(feat), min(len(feat), 20000), replace=False)]
    k = int(min(k_max, max(2, len(sample) // 400)))
    cv2.setRNGSeed(seed)
    _, _, cen = cv2.kmeans(sample, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.3), 3,
                           cv2.KMEANS_PP_CENTERS)
    lbl = np.argmin(((feat[:, None, :] - cen[None, :, :]) ** 2).sum(-1), axis=1)
    share = np.bincount(lbl, minlength=k) / len(lbl)
    keep = [i for i in range(k) if share[i] >= min_share]
    if len(keep) < 2:
        return [m]
    # the small clusters go to the nearest kept one
    lbl = np.array(keep)[np.argmin(((feat[:, None, :] - cen[keep][None, :, :]) ** 2).sum(-1), axis=1)]
    ys, xs = np.nonzero(m)
    out = []
    for i in keep:
        sm = np.zeros(m.shape, bool)
        sm[ys[lbl == i], xs[lbl == i]] = True
        out.append(sm)
    return out


def _skin_back(L, parts, within, kinds, split_kinds, de=8.0):
    """An accessory's pixels in the skin's own colours, touching the skin, given back to the skin: a part grown from a
    rough box (a mouth's part that took the chin under the lips) would print a block of the box's shape in the
    engines that lay one colour per piece. The cel styles keep an accessory as drawn and never see this."""
    if kinds is None:
        return parts
    skin_ids = [j for j, k in enumerate(kinds) if k == "skin"]
    acc_ids = [j for j, k in enumerate(kinds) if k in split_kinds]
    sk = np.isin(parts, skin_ids) & within
    if not skin_ids or not acc_ids or sk.sum() < 200:
        return parts
    main = max(skin_ids, key=lambda j: int((parts == j).sum()))
    tones, _ = part_tones(L[..., 0], sk)
    cols = np.array([np.median(L[sk & (np.abs(L[..., 0] - t) < 4)], axis=0) if (sk & (np.abs(L[..., 0] - t) < 4)).any()
                     else np.median(L[sk], axis=0) for t in tones], np.float32)
    acc = np.isin(parts, acc_ids) & within
    if not acc.any():
        return parts
    d = np.min(np.stack([np.linalg.norm(L - c, axis=2) for c in cols]), axis=0)
    like = acc & (d < de)
    if not like.any():
        return parts
    # only runs that touch the skin: a skin-coloured badge on a coat stays the badge's
    n, lab_ = cv2.connectedComponents(like.astype(np.uint8), connectivity=8)
    near = cv2.dilate(sk.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    touch = np.unique(lab_[near & like])
    back = np.isin(lab_, touch[touch > 0])
    parts = parts.copy()
    parts[back] = main
    return parts


def layers(cel, parts, within, kinds=None, min_area=30, split_kinds=("accessory",), lines=None):
    """Per part: its mask, its base tone (the one most of it has), shadow and light masks, and the Lab colour of each.
    A part of a kind in `split_kinds` with several colours gives one layer per colour piece (colour_pieces), so an
    engine that paints a layer in one colour (a wash, a block) does not turn a basket of vegetables into one blob.
    With `lines` (the line art's mask), the tones and their colours are read off the fill only, and the line pixels
    take the base: a thin part (an earring, a strap) is mostly its own outline, and read with it its colour is the
    line's. Returns a list of dicts in order of area, largest first."""
    L = lab(cel)
    Lv = L[..., 0]
    parts = _skin_back(L, parts, within, kinds, split_kinds)
    out = []
    for j in np.unique(parts[within]):
        if j == 0:
            continue
        m_all = (parts == j) & within
        if m_all.sum() < min_area:
            continue
        kind = kinds[j] if kinds is not None else None
        pieces = colour_pieces(L, m_all) if kind in split_kinds else [m_all]
        for m in pieces:
            if m.sum() < min_area:
                continue
            core = m & ~lines if lines is not None else m
            if core.sum() < max(min_area, 0.2 * m.sum()):
                core = m
            c, idx_c = part_tones(Lv, core)
            base_i = int(np.argmax(np.bincount(idx_c, minlength=len(c))))
            if core is m:
                idx = idx_c
            else:
                idx = np.abs(Lv[m][:, None] - c[None]).argmin(1).astype(np.int32)
                idx[lines[m]] = base_i
            t = np.full(m.shape, -1, np.int32)
            t[m] = idx
            cols = [np.median(L[core][idx_c == i], axis=0) if (idx_c == i).any() else L[core].mean(0)
                    for i in range(len(c))]
            out.append({"part": int(j), "kind": kind, "mask": m, "area": int(m.sum()),
                        "tone": t, "base_i": base_i, "base": m & (t == base_i), "shadow": m & (t < base_i) & (t >= 0),
                        "light": m & (t > base_i), "colours": np.array(cols, np.float32),
                        "base_lab": np.array(cols[base_i], np.float32)})
    out.sort(key=lambda d: -d["area"])
    return out
