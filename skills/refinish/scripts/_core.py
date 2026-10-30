"""Shared helpers for the refinish scripts: colour conversions, image files, the style unit, masks and filters.

Images in the engines are float32 RGB in 0..1 with a separate float32 alpha in 0..1, unless a name says otherwise
(`bgr8` is OpenCV's uint8 BGR; `lab8` is OpenCV's 8-bit Lab as float32, L in 0..255).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

# The engines' pixel constants were tuned on figures about 3000 px tall, where one style unit (a thousandth of the
# figure's height) is about 3 px. Constants that are not in a style file are scaled by px_per_u / REF_PX_PER_U.
REF_PX_PER_U = 3.0

# a console whose code page lacks a character (a Japanese kanji in a help text, on a Traditional Chinese Windows) must
# not crash a script: what it cannot print is escaped instead
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


def _utf8_out():
    enc = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "").replace("_", "")
    return enc in ("utf8", "utf8sig")


def die(msg, code=2):
    """Stop with an actionable message on stderr."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def emit(obj):
    """The script's result, as JSON on stdout: readable non-ASCII text on a UTF-8 console, escaped (\\uXXXX, still
    valid JSON) on any other."""
    print(json.dumps(obj, ensure_ascii=not _utf8_out(), indent=1))


# ------------------------------------------------------------------------------------------------------------ colour

def lab(img):
    """RGB 0..1 to CIE Lab (L 0..100)."""
    return cv2.cvtColor(np.clip(img, 0, 1).astype(np.float32), cv2.COLOR_RGB2Lab)


def rgb(lab_img):
    return np.clip(cv2.cvtColor(lab_img.astype(np.float32), cv2.COLOR_Lab2RGB), 0, 1)


def lab_px(c):
    return lab(np.array(c, np.float32).reshape(1, 1, 3))[0, 0]


def rgb_px(c):
    return rgb(np.array(c, np.float32).reshape(1, 1, 3))[0, 0]


def lab8(bgr8):
    return cv2.cvtColor(bgr8, cv2.COLOR_BGR2LAB).astype(np.float32)


def bgr8_of(lab8_img):
    return cv2.cvtColor(np.clip(lab8_img, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


# ------------------------------------------------------------------------------------------------------------- files

def load_rgba(path):
    """A picture as (rgb 0..1, alpha 0..1). A picture without alpha is opaque."""
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        die(f"cannot read the image {path}")
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.shape[2] == 4:
        alpha = im[..., 3].astype(np.float32) / 255.0
        bgr = im[..., :3]
    else:
        alpha = np.ones(im.shape[:2], np.float32)
        bgr = im
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0, alpha


def save_rgba(path, rgb_img, alpha):
    rgba = np.dstack([np.clip(rgb_img, 0, 1), np.clip(alpha, 0, 1)])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), cv2.cvtColor((rgba * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGBA2BGRA)):
        die(f"cannot write {path}")


def over(rgb_img, alpha, bg=(228, 228, 228)):
    """The picture over a flat grey, as uint8 BGR, for review boards."""
    out = rgb_img * alpha[..., None] + np.array(bg[::-1], np.float32)[None, None, :] / 255.0 * (1 - alpha[..., None])
    return cv2.cvtColor((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)


def resize_premultiplied(rgb_img, alpha, size, interpolation):
    """Resize colour premultiplied by alpha, so a cut-out's edge keeps no dark or light fringe."""
    pre = cv2.resize(rgb_img * alpha[..., None], size, interpolation=interpolation)
    a = np.clip(cv2.resize(alpha, size, interpolation=interpolation), 0, 1)
    col = np.where(a[..., None] > 1e-3, pre / np.maximum(a[..., None], 1e-3), 0)
    return np.clip(col, 0, 1).astype(np.float32), a.astype(np.float32)


# -------------------------------------------------------------------------------------------------------------- unit

class Units:
    """The style unit u: a thousandth of the subject's height (the figure's own height for a cut-out, the
    picture's height for an opaque one), so one style file paints a small sprite and a large one alike."""

    def __init__(self, alpha, head_px=None):
        ys = np.nonzero((alpha > 0.5).any(axis=1))[0]
        height = float(ys[-1] - ys[0] + 1) if len(ys) else float(alpha.shape[0])
        if head_px:                                     # a figure cut off by the frame: seven heads tall
            height = 7.0 * float(head_px)
        self.height = height
        self.px = height / 1000.0                       # pixels per unit
        self.s = self.px / REF_PX_PER_U                 # scale of the engines' own constants

    def len(self, v):
        """A length in units, in pixels."""
        return float(v) * self.px

    def area(self, v):
        """An area in square units, in square pixels."""
        return float(v) * self.px * self.px

    def k(self, v, odd=False):
        """An engine constant tuned at the reference scale, in pixels at this one."""
        n = max(1, int(round(float(v) * self.s)))
        return n | 1 if odd else n


# ------------------------------------------------------------------------------------------------------------- masks

def _perimeter(m):
    m8 = m.astype(np.uint8)
    return int((m8 & ~cv2.erode(m8, np.ones((3, 3), np.uint8))).sum())


def cut_raggedness(Lf, core, m, U):
    """How ragged a part's two-tone cut comes out: the cut's boundary length beyond that of a smoothed copy of it, per
    the part's size (the square root of its area). A cut through a soft, noisy shading follows the noise (a frayed
    edge, flecks); one along drawn shadow shapes is near its smoothed copy. On the test pictures: 25 on the skin of an
    airbrushed figure, 6 at the median of 128 parts of 20 generated figures, 21 at their most. NaN for a part with no
    cut."""
    v = Lf[core]
    if len(v) < 400:
        return float("nan")
    t = float(tone_cuts(v, 2)[0])
    cand = core & (Lf < t)
    if cand.sum() < 200 or (core & ~cand).sum() < 200:
        return float("nan")
    a = clean_shape(cand, m, U.len(0.4), U.area(4.44), U.area(4.44)) > 0.5
    s = clean_shape(a, m, U.len(1.5), U.area(30), U.area(30)) > 0.5
    return (_perimeter(a) - _perimeter(s)) / float(np.sqrt(max(1, m.sum())))


def clean_shape(cand, within, smooth, min_island, min_hole):
    """A shape as a painter lassos it: the candidate pixels smoothed into clean curves, islands and holes smaller
    than the given areas (square pixels) gone; returned with a one-pixel anti-aliased edge."""
    sm = cv2.GaussianBlur(cand.astype(np.float32), (0, 0), max(0.3, smooth))
    shape = ((sm > 0.5) & within).astype(np.uint8)
    n, lab_, st, _ = cv2.connectedComponentsWithStats(shape)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= min_island
    shape = keep[lab_].astype(np.uint8)
    holes = ((shape == 0) & within).astype(np.uint8)
    n, lab_, st, _ = cv2.connectedComponentsWithStats(holes)
    small = np.zeros(n, bool)
    small[1:] = st[1:, cv2.CC_STAT_AREA] < min_hole
    shape[small[lab_]] = 1
    a = cv2.GaussianBlur(shape.astype(np.float32), (0, 0), 0.8)
    return (np.clip((a - 0.5) * 2.5 + 0.5, 0, 1) * within).astype(np.float32)


def tone_cuts(vals, k, iters=30):
    """The steps between a part's drawn tones (shadow, base, light): the centres of k clusters of its lightness, cut
    halfway between them. For a source painted in flat tones this finds the painter's own tones."""
    v = np.sort(np.asarray(vals, np.float64))
    c = np.percentile(v, np.linspace(100.0 / (2 * k), 100 - 100.0 / (2 * k), k))
    for _ in range(iters):
        cuts = (c[:-1] + c[1:]) / 2
        idx = np.searchsorted(cuts, v)
        new = np.array([v[idx == i].mean() if (idx == i).any() else c[i] for i in range(k)])
        if np.allclose(new, c, atol=1e-5):
            break
        c = new
    return (c[:-1] + c[1:]) / 2


def ellipse_mask(h, w, items, key_centre="centre", key_radii="radii"):
    """The union of the given ellipses, each scaled by its own strength (focal areas: the face, a raised hand)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    m = np.zeros((h, w), np.float32)
    for f in items:
        (fx, fy), (rx, ry) = f[key_centre], f[key_radii]
        m = np.maximum(m, (np.hypot((xx - fx) / rx, (yy - fy) / ry) < 1).astype(np.float32) * f.get("strength", 1))
    return m


def protect_mask(subject, h, w, img, skin_mask, feather=1.5, parts=None):
    """The face's own features (eyes, mouth) kept as drawn: inside each protected box only what is not skin (lashes,
    iris, the white of the eye, the line of the mouth), so the skin around them takes the style like the rest of the
    face and no box shows. A box may set its own colour step `de` (a faint smile needs a small one).

    A feature differs from the skin in colour more than in lightness: the shade under a lip or a chin is the skin's
    own hue a little darker, so lightness counts half (on a dark skin the face's shading is many points of lightness,
    and kept as drawn it shows as a box once a style repaints the skin round it). With the part map, hair and cloth
    that run into a box from outside it (a fringe over an eye) are not features either: they are painted with their
    part, or the box's piece of them shows."""
    m = np.zeros((h, w), np.float32)
    L_img = lab(img)
    skin = np.median(L_img[skin_mask], axis=0) if skin_mask is not None and skin_mask.any() else None
    kinds = np.array([""] + [p.get("kind", "cloth") for p in subject.get("parts", [])]) if parts is not None else None
    wL = np.array([0.5, 1.0, 1.0], np.float32)
    for p in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        if skin is None:
            m[y0:y1, x0:x1] = 1
            continue
        # the skin the features are told from: the skin just round the box where there is enough of it (the warm
        # skin round a mouth, the shade under an eye are skin there, not features), else the face's median
        refs = [skin]
        r = max(4, int(0.15 * max(x1 - x0, y1 - y0)))
        ring = np.zeros((h, w), bool)
        ring[max(0, y0 - r):min(h, y1 + r), max(0, x0 - r):min(w, x1 + r)] = True
        ring[y0:y1, x0:x1] = False
        ring &= skin_mask
        if ring.sum() >= 50:
            # the skin round the box in its own tones: on two-tone skin (a cel shadow across the face) the lit and
            # the shaded tone are both skin, or the shaded side of the box is kept as drawn and its edge shows
            rv = L_img[ring]
            cut = np.median(rv[:, 0])
            lo, hi = rv[rv[:, 0] < cut], rv[rv[:, 0] >= cut]
            refs = [np.median(rv, axis=0)]
            if len(lo) >= 25 and len(hi) >= 25:
                a_, b_ = np.median(lo, axis=0), np.median(hi, axis=0)
                if np.linalg.norm(a_ - b_) > 6:
                    refs = [a_, b_]
        d = np.min(np.stack([np.linalg.norm((L_img[y0:y1, x0:x1] - ref) * wL, axis=2) for ref in refs]), axis=0)
        feat = (d > p.get("de", subject.get("protect_de", 14.0))).astype(np.uint8)
        if kinds is not None:
            # hair and cloth reaching in across the box's edge: theirs, not the face's
            pk = kinds[parts[y0:y1, x0:x1]]
            other = np.isin(pk, ("skin", "eyes", "accessory", ""), invert=True).astype(np.uint8)
            n_o, lab_o = cv2.connectedComponents(other, connectivity=8)
            if n_o > 1:
                edge = np.unique(np.concatenate([lab_o[0], lab_o[-1], lab_o[:, 0], lab_o[:, -1]]))
                feat[np.isin(lab_o, edge[edge > 0])] = 0
        feat = cv2.morphologyEx(feat, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, lab_, st, _ = cv2.connectedComponentsWithStats(feat)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 12
        k_box = cv2.dilate(keep[lab_].astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
        # faded out toward the box's own edges, so no box shows as a rectangle where what it keeps meets the
        # repainted skin (the lines over the features are laid again by every engine, so their ends are not lost)
        bh, bw = y1 - y0, x1 - x0
        mx, my = max(3.0, 0.12 * bw), max(3.0, 0.12 * bh)
        xs = np.arange(bw, dtype=np.float32)
        ys = np.arange(bh, dtype=np.float32)
        rx = np.clip(np.minimum(xs + 0.5, bw - xs - 0.5) / mx, 0, 1)
        ry = np.clip(np.minimum(ys + 0.5, bh - ys - 0.5) / my, 0, 1)
        k_box *= np.minimum(ry[:, None], rx[None, :])
        m[y0:y1, x0:x1] = np.maximum(m[y0:y1, x0:x1], k_box)
    return cv2.GaussianBlur(m, (0, 0), feather) if feather else m


def spots(h, w, items, soft=0.7):
    """Soft round spots (a blush): items are [x, y, rx, ry]; 1 inside, falling off over the outer part."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    out = np.zeros((h, w), np.float32)
    for c in items:
        cx, cy, rx = c[0], c[1], c[2]
        ry = c[3] if len(c) > 3 else rx
        d = np.hypot((xx - cx) / rx, (yy - cy) / ry)
        out = np.maximum(out, np.clip((1 - d) / soft, 0, 1))
    return out


def boundary(labels):
    """Pixels on the edge between two labels."""
    b = np.zeros(labels.shape, np.uint8)
    b[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    b[:-1, :] |= labels[:-1, :] != labels[1:, :]
    return b


# ----------------------------------------------------------------------------------------------------------- filters

def grain(gray, sigma):
    """Orientation along the picture's grain (radians) and how clear it is (0..1), from the structure tensor."""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    jxx, jyy, jxy = (cv2.GaussianBlur(v, (0, 0), sigma) for v in (gx * gx, gy * gy, gx * gy))
    along = 0.5 * np.arctan2(2 * jxy, jxx - jyy) + np.pi / 2
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / (jxx + jyy + 1e-6)
    return along.astype(np.float32), coh.astype(np.float32)


def slow_noise(rng, h, w, sigma):
    """Smooth noise in 0..1 (mean about 0.55), varying over about sigma pixels."""
    q = 8
    n = cv2.GaussianBlur(rng.random((h // q + 2, w // q + 2)).astype(np.float32), (0, 0), sigma / q)
    n = cv2.resize(n, (w, h), interpolation=cv2.INTER_CUBIC)
    return np.clip((n - n.mean()) / (n.std() + 1e-6) * 0.5 + 0.55, 0, 1)


def piece_blur(img, piece, sigma, iters=3):
    """A blur that never crosses a piece's edge: the recursive filter of Gastal & Oliveira (2011, the domain
    transform) with the pieces' boundaries as its only edges, so a stroke takes its colour from its own piece."""
    out = np.ascontiguousarray(img, np.float32).copy()
    cut_h = piece[:, 1:] != piece[:, :-1]
    cut_v = piece[1:, :] != piece[:-1, :]
    for i in range(iters):
        s = sigma * np.sqrt(3) * 2 ** (iters - i - 1) / np.sqrt(4 ** iters - 1)
        a = np.float32(np.exp(-np.sqrt(2) / s))
        for o, cut in ((out.transpose(1, 0, 2).copy(), cut_h.T), (None, cut_v)):
            if o is None:
                o = out
            wgt = np.where(cut, np.float32(0), a)[..., None]
            for x in range(1, o.shape[0]):
                o[x] += wgt[x - 1] * (o[x - 1] - o[x])
            for x in range(o.shape[0] - 2, -1, -1):
                o[x] += wgt[x] * (o[x + 1] - o[x])
            if o is not out:
                out = np.ascontiguousarray(o.transpose(1, 0, 2))
    return out


def masked_blur(v, mask, sigma):
    """A Gaussian blur of v over the mask's pixels only (the rest left as it is)."""
    num = cv2.GaussianBlur(v * mask, (0, 0), sigma)
    den = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), v)
