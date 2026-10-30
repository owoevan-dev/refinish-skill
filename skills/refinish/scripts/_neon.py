"""Neon: the figure drawn in glowing glass tubes on a dark ground. The line art of the cel base is redrawn as tubes of
one even width, each in a neon colour taken from the part beside it (its hue at full saturation; a grey or a black
part's tube burns white), with a white-hot core and a glow that spreads past the figure; the fills sink almost to
black, so the figure reads by its tubes.

The picture grows by the glow (`glow` u on every side), as a sticker grows by its border.

Style keys, section `neon`: `tube` (u, the tube's width, 2.4), `glow` (u, 9), `core` (0..1, how white the tube's centre
burns, 0.55), `fill` (0..1, how much of the fill's colour shows, 0.1), `ground` (RGB, the dark the fills sink to),
`min_line` (u², the shortest line kept, 30), `outline` (true: the silhouette is a tube too), `halo` (0..1, how far the
glow reaches past the figure into the transparent ground, 0.8); on the face (the subject's focal area) the tubes are
paler (`face_pale`, 0.55), thinner (`face_thin`, 0.4) and glow less (`face_dim`, 0.6)."""
import cv2
import numpy as np

from _core import ellipse_mask, lab
from _lines import find_lines, keep_lines


def _thin(mask):
    """Morphological skeleton (Lantuéjoul): fast, a pixel or two wide, good enough to lay a tube of even width on."""
    skel = np.zeros(mask.shape, np.uint8)
    img = mask.astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while img.any():
        er = cv2.erode(img, k)
        skel |= img & ~cv2.dilate(er, k)
        img = er
    return skel > 0


def run(subject, style, cel, alpha, parts, U, seed=7):
    ns = style.get("neon", {})
    tube = max(1.0, U.len(ns.get("tube", 2.4)))
    glow = max(1.0, U.len(ns.get("glow", 9.0)))
    pad = int(np.ceil(3 * glow)) + 2
    h, w = alpha.shape
    H, W = h + 2 * pad, w + 2 * pad
    within = alpha > 0.5
    L_line = find_lines(cel, subject.get("upscaled", 1))
    fa = np.clip(ellipse_mask(h, w, subject.get("focal", [])), 0, 1).astype(np.float32)
    face = fa > 0.5                                                  # (a face's short lines, the mouth, glow too)
    lines = keep_lines(L_line, U.area(ns.get("min_line", 30.0)), 3, always=face) > 0.3
    lines &= within
    if ns.get("outline", True):
        d = cv2.distanceTransform(within.astype(np.uint8), cv2.DIST_L2, 3)
        lines |= within & (d <= max(1.5, tube * 0.6))
    skel = _thin(lines)
    # each tube's colour: the part beside it, at full saturation; greys burn white
    fill = within & ~cv2.dilate(lines.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    _, lbl = cv2.distanceTransformWithLabels((~fill).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(fill)
    lut = np.zeros((lbl.max() + 1, 3), np.float32)
    lut[lbl[ys, xs]] = cel[ys, xs]
    near = lut[lbl]
    hsv = cv2.cvtColor((np.clip(near, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    Lb = lab(near)
    chroma = np.hypot(Lb[..., 1], Lb[..., 2])
    # the face's tubes paler, thinner and glowing less: a face's many short lines in full-strength tubes glow into one
    # mass of the skin's hue, and its eyes and mouth are lost in it (a neon sign draws a face in a few fine tubes)
    hsv[..., 1] = np.where(chroma > 10, 255 * (1 - ns.get("face_pale", 0.55) * fa), 0)
    hsv[..., 2] = 255
    neon = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32) / 255
    # the tube: an even width round the line's centre, anti-aliased, its centre burning white
    dist = cv2.distanceTransform((~skel).astype(np.uint8), cv2.DIST_L2, 3)
    tw = tube * (1 - ns.get("face_thin", 0.4) * fa)
    t_a = np.clip(tw / 2 + 0.5 - dist, 0, 1)
    core = np.clip(1 - dist / np.maximum(0.5, tw / 4), 0, 1) * float(ns.get("core", 0.55))
    tube_rgb = neon * (1 - core[..., None]) + core[..., None]
    # the fills sunk to a dark ground, a little of their colour left
    ground = np.array(ns.get("ground", [14, 12, 24]), np.float32) / 255
    f = float(ns.get("fill", 0.1))
    body = ground * (1 - f) + cel * f
    out = np.zeros((H, W, 3), np.float32)
    A = np.zeros((H, W), np.float32)
    sl = (slice(pad, pad + h), slice(pad, pad + w))
    out[sl] = body * alpha[..., None]
    A[sl] = alpha
    T = np.zeros((H, W), np.float32)
    T[sl] = t_a
    C = np.zeros((H, W, 3), np.float32)
    C[sl] = tube_rgb * t_a[..., None]
    out = out * (1 - T[..., None]) + C
    # the glow: the tubes' light spread in two widths, added like light
    src = np.zeros((H, W, 3), np.float32)
    src[sl] = neon * (t_a * (1 - ns.get("face_dim", 0.6) * fa))[..., None]
    g = cv2.GaussianBlur(src, (0, 0), glow * 0.45) * 0.9 + cv2.GaussianBlur(src, (0, 0), glow) * 0.8
    out = 1 - (1 - out) * (1 - np.clip(g, 0, 1))
    gl = np.clip(g.max(axis=2) * float(ns.get("halo", 0.8)), 0, 1)
    A = np.maximum(A, gl)
    # straight colour where only the glow is: the light itself
    only = A > 1e-4
    out = np.where(only[..., None], np.clip(out, 0, 1), 0.0)
    return out.astype(np.float32), {"alpha": A.astype(np.float32), "size": [W, H], "pad": pad,
                                    "tubes_px": int((t_a > 0.5).sum())}
