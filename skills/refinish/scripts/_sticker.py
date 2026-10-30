"""A die-cut sticker: the figure in its finish (the style's `base`, TV cel by default) on a white vinyl border that
follows its outline, cut smooth the way a cutting plotter cuts it (the notches between an arm and the body closed,
the corners rounded), a soft shadow under it, a faint sheen across the vinyl.

The picture grows by the border and the shadow: the result is larger than the source, so a sticker cannot be mixed
in a recipe or composited at the source's size.

Style keys, section `sticker`: `border` (u, 18), `round` (u, how far the cut closes the outline's notches, 14),
`colour` (RGB 0..255, the vinyl, white), `edge` (RGB of the cut edge's thin line, or null; light grey),
`shadow` ({"offset": [dx, dy] u, "blur": u, "opacity": 0..1}), `sheen` (0..1, the vinyl's gloss, 0.06)."""
import cv2
import numpy as np


def _disk(r):
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def run(subject, style, cel, alpha, parts, U, seed=7):
    st = style.get("sticker", {})
    b = U.len(st.get("border", 18.0))
    rnd = U.len(st.get("round", 14.0))
    sh = {"offset": [2.5, 4.0], "blur": 5.0, "opacity": 0.3, **(st.get("shadow") or {})}
    dx, dy = U.len(sh["offset"][0]), U.len(sh["offset"][1])
    sb = U.len(sh["blur"])
    pad = int(np.ceil(b + rnd + max(abs(dx), abs(dy)) + 3 * sb)) + 4
    h, w = alpha.shape
    H, W = h + 2 * pad, w + 2 * pad
    A = np.zeros((H, W), np.float32)
    A[pad:pad + h, pad:pad + w] = alpha
    C = np.zeros((H, W, 3), np.float32)
    C[pad:pad + h, pad:pad + w] = cel
    m = (A > 0.5).astype(np.uint8)

    # the cut: the outline grown by the border, its notches closed, its corners rounded, anti-aliased
    cut = cv2.dilate(m, _disk(b))
    if rnd > 0:
        big = cv2.copyMakeBorder(cut, int(rnd) + 2, int(rnd) + 2, int(rnd) + 2, int(rnd) + 2, cv2.BORDER_CONSTANT, 0)
        big = cv2.morphologyEx(big, cv2.MORPH_CLOSE, _disk(rnd))
        cut = big[int(rnd) + 2:-(int(rnd) + 2), int(rnd) + 2:-(int(rnd) + 2)]
    soft = cv2.GaussianBlur(cut.astype(np.float32), (0, 0), max(1.0, b / 6))
    cut_a = np.clip((soft - 0.5) * 4 + 0.5, 0, 1)

    # the shadow: the cut moved away from the light and blurred
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    shadow = cv2.warpAffine(cut_a, M, (W, H))
    shadow = cv2.GaussianBlur(shadow, (0, 0), max(0.5, sb)) * float(sh["opacity"])

    vinyl = np.array(st.get("colour", [255, 255, 255]), np.float32) / 255
    # "over" in premultiplied colour, bottom to top: the shadow (black), the vinyl, its cut edge, the figure
    P = np.zeros((H, W, 3), np.float32)
    a = shadow.copy()
    P = vinyl * cut_a[..., None] + P * (1 - cut_a[..., None])
    a = cut_a + a * (1 - cut_a)
    edge_c = st.get("edge", [205, 205, 205])
    if edge_c is not None:
        ring = np.clip(cut_a - cv2.erode(cut_a, _disk(max(1.0, U.len(0.7)))), 0, 1) * 0.8
        P = P * (1 - ring[..., None]) + np.array(edge_c, np.float32) / 255 * ring[..., None]
    P = C * A[..., None] + P * (1 - A[..., None])
    a = A + a * (1 - A)
    out = P / np.maximum(a, 1e-4)[..., None]

    # the vinyl's sheen: one soft diagonal band of light across the sticker
    sheen = float(st.get("sheen", 0.06))
    if sheen > 0:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        t = (xx / W + yy / H) / 2
        band = (np.exp(-((t - 0.32) / 0.09) ** 2) * sheen * cut_a)[..., None]
        out = 1 - (1 - out) * (1 - band)
    return np.clip(out, 0, 1).astype(np.float32), {"alpha": np.clip(a, 0, 1).astype(np.float32),
                                                   "size": [W, H], "pad": pad}
