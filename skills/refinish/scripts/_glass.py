"""Stained glass: the figure as pieces of coloured glass held in lead. Each part's tone areas of the cel base are cut
into pieces (a large area split again, the way a glazier cuts a sheet to fit), each piece one colour of glass,
luminous, uneven within (streaks and a darker rim where the glass is thicker), the lead came between them dark with a
thin light along its crown. The line art is painted on the glass as thin dark trace lines (grisaille), the way a
glass painter draws strands and folds; the skin is not cut, and the eyes and the mouth are kept as drawn.

Style keys, section `glass`: `piece` (u, the side of a typical piece, 70), `lead` (u, half the came's width, 0.8), `paint` (0..1, the
grisaille trace lines' strength, 0.85),
`lead_colour` (RGB), `saturation` (1.25), `light` (0..1, how luminous the glass, 0.25), `vary` (how much the sheets differ
in lightness and hue, 1.0), `texture` (0..1, 0.5),
`grisaille` (kinds painted on whole glass instead of cut, ["skin"])."""
import cv2
import numpy as np

import _flat
import _texture as tx
from _core import lab, protect_mask, rgb
from _lines import find_lines


def _cells(mask, area_px, rng):
    """A piece cut into cells of about `area_px` each: k-means on its pixels' positions (convex, glazier-like)."""
    ys, xs = np.nonzero(mask)
    n = int(round(len(xs) / max(1.0, area_px)))
    if n < 2:
        return [mask]
    pts = np.stack([xs, ys], 1).astype(np.float32)
    sub = pts[rng.choice(len(pts), min(len(pts), 6000), replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    cv2.setRNGSeed(int(rng.integers(1 << 30)))
    _, _, cen = cv2.kmeans(sub, min(n, 40), None, crit, 2, cv2.KMEANS_PP_CENTERS)
    d = ((pts[:, None, :] - cen[None]) ** 2).sum(2)
    lab_ = d.argmin(1)
    out = []
    for i in range(len(cen)):
        m = np.zeros(mask.shape, bool)
        m[ys[lab_ == i], xs[lab_ == i]] = True
        if m.any():
            out.append(m)
    return out


def run(subject, style, cel, alpha, parts, U, seed=7):
    gs = style.get("glass", {})
    rng = np.random.default_rng(seed)
    h, w = alpha.shape
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    gris = set(gs.get("grisaille", ["skin"]))
    piece_px = U.area(gs.get("piece", 70.0) ** 2)
    pieces = []                                         # (mask, Lab colour, painted on whole)
    for lay in _flat.layers(cel, parts, within, kinds):
        whole = lay["kind"] in gris
        if whole:
            pieces.append((lay["mask"], lay["base_lab"], True))
            continue
        for i, col in enumerate(lay["colours"]):
            m = lay["mask"] & (lay["tone"] == i)
            n_, cc = cv2.connectedComponents(m.astype(np.uint8), connectivity=8)
            for c in range(1, n_):
                piece = cc == c
                if piece.sum() < U.area(6):
                    continue
                for cell in _cells(piece, piece_px, rng):
                    pieces.append((cell, col, False))
    sat, light = float(gs.get("saturation", 1.25)), float(gs.get("light", 0.25))
    Lc = lab(cel)
    out_lab = Lc.copy()
    label = np.zeros((h, w), np.int32)
    streak = tx.fbm(rng, h, w, U.len(14.0), octaves=3)
    streak = cv2.GaussianBlur(streak, (0, 0), U.len(1.0), sigmaY=U.len(6.0))
    for k, (m, col, whole) in enumerate(pieces, start=1):
        label[m] = k
        if whole:
            # painted glass: the cel's own shading kept, a little lighter, like light through it
            out_lab[m, 0] = np.clip(Lc[m, 0] + light * 10, 0, 100)
            continue
        c = np.array(col, np.float32)
        # every sheet of glass a little different: its lightness and its hue (a few degrees), as panes cut from
        # different sheets of one colour are; a grey glass stays a grey of its own tint
        dl = rng.normal(0, 1) * 4.0 * float(gs.get("vary", 1.0))
        dh = np.radians(rng.normal(0, 1) * 7.0 * float(gs.get("vary", 1.0)))
        a0, b0 = c[1] * sat, c[2] * sat
        a1, b1 = a0 * np.cos(dh) - b0 * np.sin(dh), a0 * np.sin(dh) + b0 * np.cos(dh)
        Lp = np.clip(c[0] + light * (100 - c[0]) * 0.35 + dl, 5, 96)
        out_lab[m] = [Lp, a1, b1]
        # light through the glass: brighter in the middle of the piece, darker toward the lead
        ys_, xs_ = np.nonzero(m)
        if len(xs_) > 30:
            d_ = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 3)[ys_, xs_]
            t = np.clip(d_ / max(1.0, np.percentile(d_, 90)), 0, 1)
            out_lab[ys_, xs_, 0] = np.clip(out_lab[ys_, xs_, 0] + (t - 0.5) * 9 * light / 0.25, 3, 98)
    # within each piece: streaks, and a darker rim where the glass is thick at the lead
    tex = float(gs.get("texture", 0.5))
    edge = np.zeros((h, w), bool)                       # (one pixel per cut: where the right or lower neighbour differs)
    edge[:, :-1] |= label[:, :-1] != label[:, 1:]
    edge[:-1, :] |= label[:-1, :] != label[1:, :]
    rim = cv2.distanceTransform((~edge).astype(np.uint8), cv2.DIST_L2, 3)
    rim_k = np.clip(1 - rim / max(1.0, U.len(6.0)), 0, 1)
    cut = label > 0
    gris_mask = np.zeros((h, w), bool)
    for m, _, whole in pieces:
        if whole:
            gris_mask |= m
    glass_px = cut & ~gris_mask
    out_lab[..., 0] = np.where(glass_px, out_lab[..., 0] * (1 + 0.06 * tex * streak) - 9 * tex * rim_k, out_lab[..., 0])
    out = np.clip(rgb(out_lab), 0, 1)
    # the eyes and the mouth as drawn on their glass
    prot = protect_mask(subject, h, w, cel, np.isin(parts, [j for j, k in enumerate(kinds) if k == "skin"]),
                        parts=parts)
    out = out * (1 - prot[..., None]) + cel * prot[..., None]
    # the lead: every cut between pieces and the figure's outline, one even width; the eyes and the mouth are never
    # leaded over
    lw = max(1, int(round(U.len(gs.get("lead", 0.8)))))   # (the came's half-width; the cut line is its centre)
    lead = edge & within & (prot < 0.3)
    d_in = cv2.distanceTransform(within.astype(np.uint8), cv2.DIST_L2, 3)
    lead |= within & (d_in <= lw)
    lead_w = cv2.dilate(lead.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * lw + 1, 2 * lw + 1)))
    lead_a = np.clip(cv2.GaussianBlur(lead_w.astype(np.float32), (0, 0), 0.7), 0, 1)[..., None]
    lead_c = np.array(gs.get("lead_colour", [30, 30, 34]), np.float32) / 255
    crown = (cv2.distanceTransform(lead_w, cv2.DIST_L2, 3) >= lw * 0.8).astype(np.float32)
    crown = cv2.GaussianBlur(crown, (0, 0), 0.8)[..., None] * 0.25
    # the drawing painted on the glass in vitreous paint (grisaille): the line art as thin dark trace lines on every
    # piece, so the strands of hair, the folds and the face read as the glass painter drew them
    L_line = find_lines(cel, subject.get("upscaled", 1))
    paint = (np.clip(L_line * 1.2, 0, 1) * within * (1 - prot))[..., None] * float(gs.get("paint", 0.85))
    out = out * (1 - paint) + np.array([0.13, 0.09, 0.08], np.float32) * paint
    out = out * (1 - lead_a) + (lead_c + crown) * lead_a
    return np.clip(out, 0, 1).astype(np.float32), {"pieces": len(pieces)}
