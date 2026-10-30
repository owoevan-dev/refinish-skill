"""Paper cut: the figure built from layers of cut coloured paper. Each part's tone areas of the cel base become sheets
of paper in a few flat colours, their edges cut clean and a little simplified (a blade's curve, not the drawing's every
wobble), stacked with a soft drop shadow under each sheet onto the one below, the paper's fibre showing faintly.
Nothing is drawn: no line art, only the cut edges and their shadows; the eyes and the mouth are cut as small pieces
too, from their own colours.

Style keys, section `papercut`: `simplify` (u, how much a cut edge is smoothed, 2.5), `min_piece` (u², the smallest
piece cut, 25), `shadow` ({"offset": [dx, dy] u (1.6, 2.6), "blur": u (2.4), "opacity" (0.6)}), `fibre` (0..1, 0.35), `paper` (the sheets'
texture kind, "washi"), `colours` (how many flat colours per part, at most 3), `chroma` (1.0)."""
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
    # the colours read off the fills, not the outlines (a thin part's colour is otherwise its line's)
    lines = find_lines(cel, subject.get("upscaled", 1)) > 0.3
    for lay in _flat.layers(cel, parts, within, kinds, lines=lines):
        rr = _radius(lay["mask"], r)
        base = _smooth(lay["mask"], rr) & within
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
    hole = _smooth(within, r) & ~cv2.dilate(covered.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    if hole.any():
        out[hole] = cel[hole]
    # the eyes and the mouth: small pieces in their own colours, as cut (the drawn features, kept)
    prot = protect_mask(subject, h, w, cel, np.isin(parts, [j for j, k in enumerate(kinds) if k == "skin"]),
                        parts=parts)
    out = out * (1 - prot[..., None]) + cel * prot[..., None]
    # the paper's fibre, faint, everywhere
    fib = float(ps.get("fibre", 0.35))
    if fib > 0:
        hgt, _ = tx.paper(ps.get("paper", "washi"), h, w, U, seed=seed)
        out = out * tx.lit(hgt, U, 0.06 * fib / 0.35)[..., None]
    # the figure's own outer cut: its silhouette smoothed the same way
    sil = _smooth(within, r).astype(np.float32)
    a_out = np.clip(cv2.GaussianBlur(sil, (0, 0), 0.6), 0, 1)
    return np.clip(out, 0, 1).astype(np.float32), {"alpha": a_out.astype(np.float32), "sheets": len(sheets)}
