"""Line art: finding the source's lines, keeping the ones worth keeping, the closed outline, and laying lines again
in one of three colourings (own: each line a dark shade of its own drawn colour; ink: one dark ink, warmer by skin;
trace: each line a dark shade of the fill beside it, the anime 色トレス)."""
import cv2
import numpy as np

from _core import lab, rgb


def gray(img):
    return cv2.cvtColor(np.clip(img, 0, 1).astype(np.float32), cv2.COLOR_RGB2GRAY)


def line_strength(img, size=7, lo=0.12, hi=0.32):
    """How much each pixel is part of the line art: thin marks darker than what surrounds them (black top-hat),
    measured relative to the surroundings so the lines inside dark hair count as much as those on skin."""
    g = gray(img)
    closed = cv2.morphologyEx(g, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    rel = (closed - g) / (closed + 0.06)
    return np.clip((rel - lo) / (hi - lo), 0, 1).astype(np.float32)


def colour_edges(img, thresh=0.10):
    """Strong colour changes, to split regions where the line art has a gap."""
    lb = cv2.GaussianBlur(lab(img), (0, 0), 1.2)
    a, b = lb[..., 1] / 100.0, lb[..., 2] / 100.0
    ga = np.hypot(cv2.Sobel(a, cv2.CV_32F, 1, 0), cv2.Sobel(a, cv2.CV_32F, 0, 1))
    gb = np.hypot(cv2.Sobel(b, cv2.CV_32F, 1, 0), cv2.Sobel(b, cv2.CV_32F, 0, 1))
    return (np.hypot(ga, gb) > thresh).astype(np.uint8)


def meanshift(img, sp, sr):
    u8 = cv2.cvtColor((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(cv2.pyrMeanShiftFiltering(u8, sp, sr), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def find_lines(img, upscaled=1, simplify=(3, 9), lo=0.18, crisp=None):
    """The source's line art, 0..1: thin marks darker than their surroundings after a light mean shift (faint
    strands and speckle gone, strong lines kept). A picture upscaled the traditional way has its lines as many times
    wider and softer as it was enlarged: the finder looks that many times wider, and `crisp` (two cut points) makes
    soft line edges crisp again."""
    up = max(1, upscaled)
    Ls = line_strength(meanshift(img, int(simplify[0] * up), simplify[1]), size=int(5 * up) | 1)
    L = np.clip((Ls - lo) / (1 - lo), 0, 1).astype(np.float32)
    if crisp and up > 1:
        c0, c1 = crisp
        L = np.clip((L - c0) / (c1 - c0), 0, 1)
    return L


def keep_lines(L_line, min_area, reach=3, by_part=None, always=None):
    """The lines worth keeping: components of at least min_area pixels (by_part: (mask, min_area) pairs for lines
    lying mostly in a part, the long locks of hair), every line touching `always` (the face) kept; the kept lines'
    soft edges within `reach` pixels."""
    on = (L_line > 0.3).astype(np.uint8)
    n, lab_, cst, _ = cv2.connectedComponentsWithStats(on, connectivity=8)
    areas = np.maximum(cst[:, cv2.CC_STAT_AREA], 1)
    need = np.full(n, float(min_area))
    for mask, ma in (by_part or []):
        share = np.bincount(lab_.ravel(), weights=mask.ravel().astype(np.float64), minlength=n)
        need[share > 0.5 * areas] = ma
    keep = cst[:, cv2.CC_STAT_AREA] >= need
    if always is not None:
        keep |= np.bincount(lab_.ravel(), weights=always.ravel().astype(np.float64), minlength=n) > 0
    keep[0] = False
    near = cv2.dilate(keep[lab_].astype(np.uint8), np.ones((reach, reach), np.uint8)).astype(np.float32)
    return L_line * near


def reversed_lines(line, solid, margin, min_area=0.0):
    """The lines that run inside a solid black mass, to be cut out of it (0..1).

    Two black legs crossing, a fold in a black coat, a black skirt over black tights: drawn black on black, such a line
    vanishes and the mass reads as one shape. A manga artist draws it in white on the solid black (ホワイト), and a
    block cutter leaves it uncut in the sumi block (白抜き). The mass's own edge keeps its dark line: only lines at
    least `margin` px inside `solid` (a bool mask, the solid areas of every part that is not hair) reverse, and only
    pieces of at least `min_area` px: an artist whites out the edges and the overlaps, not every fleck of a fold."""
    if margin < 1 or not solid.any():
        return np.zeros(line.shape, np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(round(margin)) + 1,) * 2)
    inside = cv2.erode(solid.astype(np.uint8), k) > 0
    core = ((line > 0.5) & inside).astype(np.uint8)
    if min_area > 0:
        n, lab_, st, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
        keep = st[:, cv2.CC_STAT_AREA] >= min_area
        keep[0] = False
        core = keep[lab_].astype(np.uint8)
    return np.clip(cv2.GaussianBlur(core.astype(np.float32), (0, 0), 0.6) * 1.4, 0, 1)


def closed_outline(alpha, width, smooth=3, min_len=40):
    """The figure's outline as one closed line of even width just inside the silhouette, on every side: where the
    picture drew no line (a lit edge, a rim light) as much as where it did, the way an animation drawing is lined all
    round so the paint has a closed area to fill. The cut-out's edge at alpha 0.5, smoothed along its length, drawn
    twice as wide and centred on the edge; the half outside falls where the figure is transparent."""
    # a figure cut by the picture's edge (a bust, a medium close-up) is not outlined along the cut: the mask is carried
    # on past the edge, so its contour runs outside the picture there
    pad = int(2 * width + smooth + 4)
    mask = cv2.copyMakeBorder((alpha > 0.5).astype(np.uint8), pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    canvas = np.zeros(mask.shape, np.uint8)
    for cnt in contours:
        if len(cnt) < min_len:
            continue
        pts = cnt[:, 0, :].astype(np.float32)
        k = smooth
        sm = np.stack([np.convolve(np.r_[pts[-k:, i], pts[:, i], pts[:k, i]], np.ones(2 * k + 1) / (2 * k + 1), "valid")
                       for i in range(2)], 1)
        cv2.polylines(canvas, [np.int32(np.round(sm * 4))], True, 255, max(1, int(round(2 * width))), cv2.LINE_AA, shift=2)
    return canvas[pad:-pad, pad:-pad].astype(np.float32) / 255.0


def thicken_outer(a, within, thicken, band):
    """Lines near the silhouette drawn a little heavier, as an animator's outer contour."""
    if not thicken:
        return a
    mm = within.astype(np.uint8)
    near = np.clip(1 - np.minimum(cv2.distanceTransform(mm, cv2.DIST_L2, 5),
                                  cv2.distanceTransform(1 - mm, cv2.DIST_L2, 5)) / band, 0, 1)
    k = 2 * int(round(thicken)) + 1
    return np.maximum(a, cv2.dilate(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) * near * 0.9)


# ---------------------------------------------------------------------------------------------------------- colours

def fill_under(img, L, sigma=2.4):
    """The colour of the fill around each line pixel: a blur that ignores the line pixels."""
    wgt = np.clip(1 - L * 2.2, 0, 1)
    num = cv2.GaussianBlur(img * wgt[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(wgt, (0, 0), sigma)[..., None]
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), img).astype(np.float32)


def trace_colour(fill, dark=0.5, cap=42.0, floor=5.0, chroma=1.4, neutral_bias=(3.0, -8.0)):
    """色トレス: a darker, richer shade of the fill beside the line; lines between near-neutral fills (white shirts,
    grey walls) lean blue-violet, as painters colour them."""
    f = lab(fill)
    c = np.hypot(f[..., 1], f[..., 2])
    neutral = np.clip(1 - c / 22.0, 0, 1)
    Ll = np.clip(f[..., 0] * dark, floor, cap)
    return rgb(np.stack([Ll, f[..., 1] * chroma + neutral_bias[0] * neutral, f[..., 2] * chroma + neutral_bias[1] * neutral], -1))


def alpha_of(L_new, strength):
    return np.clip(L_new * 1.15 * strength, 0, 1) ** 0.9


def lay_trace(base, L, within, strength=1.0, thicken=1, band=5.0, **colour):
    """Lift the old lines off `base`, mend the fills under them, and lay the new lines in the fill's darker shade."""
    a = thicken_outer(alpha_of(L, strength), within, thicken, band)
    fill = fill_under(base, L)
    lift = cv2.GaussianBlur(np.clip(cv2.dilate((L > 0.12).astype(np.float32), np.ones((3, 3), np.uint8)), 0, 1), (0, 0), 0.7)
    mended = base * (1 - lift[..., None]) + fill * lift[..., None]
    col = trace_colour(fill, **colour)
    return (mended * (1 - a[..., None]) + col * a[..., None]).astype(np.float32)


def lay_ink(base, L, within, ink, by=(), strength=1.0, thicken=2, band=6.0):
    """One dark ink (Lab), with other inks blended in where given masks lie (warmer by skin, deep blue in hair)."""
    a = thicken_outer(alpha_of(L, strength), within, thicken, band)
    col = np.empty_like(base)
    col[:] = rgb(np.array(ink, np.float32).reshape(1, 1, 3))[0, 0]
    for mask, c in by:
        m = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 2.0)[..., None]
        col = col * (1 - m) + rgb(np.array(c, np.float32).reshape(1, 1, 3))[0, 0] * m
    return base * (1 - a[..., None]) + col * a[..., None]


def lay_own(base, src, L, within, strength=1.0, L_ink=16.0, chroma=0.9, gap=9.0, floor=3.0):
    """Each line in a dark shade of its own drawn colour (navy in the hair, brown on the skin, the fill's own hue
    where only the closed outline runs), all at one darkness: a line keeps the part it was drawn for. A line is never
    lighter than `gap` below the paint beside it: on black tights or black hair a line at the one darkness would sink
    into the fill (two crossed legs would read as one), so there it goes as dark as the fill needs, down to `floor`."""
    a = alpha_of(L, strength)
    on = ((L > 0.05) & within).astype(np.float32)                      # (a transparent pixel's colour is noise)
    num = cv2.GaussianBlur(lab(src) * on[..., None], (0, 0), 1.5)
    den = cv2.GaussianBlur(on, (0, 0), 1.5)[..., None]
    f = np.where(den > 1e-3, num / np.maximum(den, 1e-3), lab(src))
    fill_L = lab(fill_under(base, L))[..., 0]
    f[..., 0] = np.minimum(L_ink, np.maximum(floor, fill_L - gap))
    f[..., 1:] *= chroma
    return base * (1 - a[..., None]) + rgb(f) * a[..., None]
