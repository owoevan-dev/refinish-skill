"""Paper cut: the figure built from layers of cut coloured paper. Each part's tone areas of the cel base become sheets
of paper in a few flat colours, their edges cut clean and a little simplified (a blade's curve, not the drawing's every
wobble), stacked with a soft drop shadow under each sheet onto the one below, the paper's fibre showing faintly. The
figure's outer edge is cut the same way, and what it closes (the gaps between loose strands of hair) is paper of the
sheet beside it. Nothing is drawn: no line art, only the cut edges and their shadows; the eyes and the mouth are laid
over the face's paper as drawn.

Style keys, section `papercut`: `simplify` (u, how much a cut edge is smoothed, 2.5), `min_piece` (u², the smallest
piece cut, 25), `shadow` ({"offset": [dx, dy] u (1.6, 2.6), "blur": u (2.4), "opacity" (0.6)}), `fibre` (0..1, 0.35),
`paper` (the sheets' texture kind, "washi"), `chroma` (1.0)."""
import cv2
import numpy as np

import _flat
import _texture as tx
from _core import lab, protect_mask, rgb
from _lines import find_lines


def _smooth(m, r):
    """A cut edge: the mask's outline smoothed at radius r (a blur and a threshold), so it reads as cut, not traced."""
    if r < 0.5:
        return m
    s = cv2.GaussianBlur(m.astype(np.float32), (0, 0), r)
    return s > 0.5


def _radius(m, r):
    """The smoothing a piece can take: a thin piece (a cord, a strap) cut with the blade's usual curve would vanish
    under it, so its curve is no wider than about half its own width."""
    if not m.any():
        return r
    dt = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 3)
    half = float(np.percentile(dt[m], 95))
    return min(r, max(0.5, 0.6 * half))


def _features(subject, parts, kinds, h, w):
    """Where the drawn eyes are: the parts of the eyes' kind that lie mostly inside the protected boxes, all of each
    (what a hint grew outside the boxes, into a cheek, is no eye). Nothing without boxes."""
    inbox = np.zeros((h, w), bool)
    for p in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        inbox[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    feat = np.zeros((h, w), bool)
    if inbox.any():
        for j, k in enumerate(kinds):
            m = parts == j
            if k == "eyes" and m.any() and (m & inbox).sum() > 0.5 * m.sum():
                feat |= m
    return feat


def _filled(m, k):
    """The mask closed at k px with its holes filled: an eye's whole shape, a strand across it included."""
    c = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    ff = np.pad(c, 1)
    cv2.floodFill(ff, np.zeros((ff.shape[0] + 2, ff.shape[1] + 2), np.uint8), (0, 0), 1)
    return c.astype(bool) | (ff[1:-1, 1:-1] == 0)


def run(subject, style, cel, alpha, parts, U, seed=7):
    ps = style.get("papercut", {})
    h, w = alpha.shape
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    r = U.len(ps.get("simplify", 2.5))
    min_px = U.area(ps.get("min_piece", 25.0))
    sh = {"offset": [1.6, 2.6], "blur": 2.4, "opacity": 0.6, **(ps.get("shadow") or {})}
    dx, dy, sb = U.len(sh["offset"][0]), U.len(sh["offset"][1]), U.len(sh["blur"])
    chroma = float(ps.get("chroma", 1.0))
    # the sheets, bottom to top: each part's base tone over its whole area, then its shadow and light pieces over it;
    # the largest parts first (the body under the arms and the hair over the face, as a paper artist layers them)
    sheets = []
    skin = np.isin(parts, [j for j, k in enumerate(kinds) if k == "skin"])
    # the eyes are laid over the paper as drawn (below), so the paper under them is the face's: an eye's part cut
    # as a sheet of its own shows round the drawing and casts its shadow under it, a dark ring round the eye
    feat = _features(subject, parts, kinds, h, w) & within
    s_parts, s_cel = parts, cel
    if feat.any() and skin.any():
        _, near = cv2.distanceTransformWithLabels((~skin).astype(np.uint8), cv2.DIST_L2, 5,
                                                  labelType=cv2.DIST_LABEL_PIXEL)
        lut = np.zeros(int(near.max()) + 1, np.int32)
        lut[near[skin]] = parts[skin]
        s_parts, s_cel = parts.copy(), cel.copy()
        s_parts[feat] = lut[near[feat]]
        s_cel[feat] = np.median(cel[skin], axis=0)
    # the colours read off the fills, not the outlines (a thin part's colour is otherwise its line's)
    lines = find_lines(s_cel, subject.get("upscaled", 1)) > 0.3
    lays = _flat.layers(s_cel, s_parts, within, kinds, lines=lines)
    # the figure's outer cut, smoothed like every sheet's: what it closes beyond the drawing (the gaps between loose
    # strands of hair) is cut from the sheet beside it, else no sheet covers it and the colour hidden there shows
    cut = _smooth(within, r)
    gap = np.full((h, w), -1, np.int32)
    closed = cut & ~within
    if closed.any() and lays:
        owner = np.full((h, w), -1, np.int32)
        for k, lay in enumerate(lays):
            owner[lay["mask"]] = k
        _, near = cv2.distanceTransformWithLabels((owner < 0).astype(np.uint8), cv2.DIST_L2, 5,
                                                  labelType=cv2.DIST_LABEL_PIXEL)
        lut = np.full(int(near.max()) + 1, -1, np.int32)
        lut[near[owner >= 0]] = owner[owner >= 0]
        gap[closed] = lut[near[closed]]
    for k, lay in enumerate(lays):
        rr = _radius(lay["mask"], r)
        base = (_smooth(lay["mask"], rr) & within) | (gap == k)
        sheets.append((base, lay["base_lab"]))
        for i, col in enumerate(lay["colours"]):
            if i == lay["base_i"]:
                continue
            m = _smooth(lay["mask"] & (lay["tone"] == i), rr) & base
            if m.sum() >= min_px:
                sheets.append((m, col))
    out = np.zeros((h, w, 3), np.float32)
    out[:] = np.array([1.0, 1.0, 1.0], np.float32)
    covered = np.zeros((h, w), bool)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    for m, col in sheets:
        c = np.array(col, np.float32).copy()
        c[1:] *= chroma
        colour = rgb(c.reshape(1, 1, 3))[0, 0]
        # the sheet's shadow on what lies under it (only where there is paper under it): a sheet lifted off the one
        # below casts a soft dark band along its lower and right edges
        s_ = cv2.warpAffine(m.astype(np.float32), M, (w, h))
        s_ = cv2.GaussianBlur(s_, (0, 0), max(0.5, sb)) * float(sh["opacity"]) * (covered & ~m)
        out = out * (1 - s_[..., None])
        a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.6)[..., None]
        out = out * (1 - a) + colour * a
        covered |= m
    # what no sheet covers inside the figure (a sliver between two cut edges): the colour the cel base has there, not
    # bare white paper showing through the figure
    hole = cut & ~cv2.dilate(covered.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    if hole.any():
        out[hole] = cel[hole]
    # the eyes and the mouth, laid on the paper as drawn
    prot = protect_mask(subject, h, w, cel, skin, parts=parts)
    if feat.any():
        # in a box with an eye, the eye alone as drawn (a strand across it included): the rest of the box is paper
        # like the rest of the face. A strand of the fringe beside the eye, pasted where the paper fringe has been
        # simplified away, shows faint and broken, and the drawing's light edges round it as white flecks
        eye = cv2.dilate(_filled(feat, max(2, int(round(U.len(2.0))))).astype(np.uint8), np.ones((3, 3), np.uint8),
                         iterations=max(1, int(round(U.len(1.0)))))
        eye = cv2.GaussianBlur(eye.astype(np.float32), (0, 0), 1.0)
        boxed = np.zeros((h, w), np.uint8)
        for p in subject.get("protect", []):
            x0, y0, x1, y1 = (max(0, int(v)) for v in p["box"])
            if feat[y0:y1, x0:x1].any():
                boxed[y0:y1, x0:x1] = 1
        boxed = cv2.dilate(boxed, np.ones((9, 9), np.uint8)).astype(bool)
        prot = np.where(boxed, prot * eye, prot)
    out = out * (1 - prot[..., None]) + cel * prot[..., None]
    # the paper's fibre, faint, everywhere
    fib = float(ps.get("fibre", 0.35))
    if fib > 0:
        hgt, _ = tx.paper(ps.get("paper", "washi"), h, w, U, seed=seed)
        out = out * tx.lit(hgt, U, 0.06 * fib / 0.35)[..., None]
    # the figure's own outer cut: its silhouette smoothed the same way
    sil = cut.astype(np.float32)
    a_out = np.clip(cv2.GaussianBlur(sil, (0, 0), 0.6), 0, 1)
    return np.clip(out, 0, 1).astype(np.float32), {"alpha": a_out.astype(np.float32), "sheets": len(sheets)}
