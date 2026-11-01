"""An eye split into its iris, its white and its lashes by a promptable segmenter (SAM 2), clicked where the eye's own
tones put the iris and the white; and the eyes worth a second look.

The iris is found by its shape, not by a tone. A pale grey-blue iris can be as light as a white shaded grey, and a dark
iris under the lash line as dark as the lashes, so no threshold of lightness or chroma parts them in every drawing. What
does part them: the iris is like neither the eye's white nor its lashes. The click goes to the middle of the eye's area
farthest from both, and the segmenter returns the round object there, as the foundation-model approach to iris
segmentation does (Iris-SAM, arXiv:2402.06497) where the classical one fitted a circle to the iris's edge (Daugman 2004,
"How iris recognition works"). The white is clicked next, on what is like the eye's white outside the iris, and taken
out of the iris; what is left in the eye and is like its lashes is the lashes.

An eye whose split looks wrong by its own proportions is flagged (`doubts`), for whoever looks at the result to click
the iris and the white by hand, or to keep the eye as drawn: no iris; an iris under IRIS_SMALL of the eye (the
segmenter took a catchlight or a pupil); lashes over LASH_HEAVY times the iris (the iris's shaded upper half read as
lashes); a white under NO_WHITE of the eye (the white taken into the iris). They were set on 34 eyes (17 pictures) and
are signs, not proofs: an eye drawn half closed has little white and is flagged though it is right.

The segmenter is a callable: predict(points, labels) -> (masks, scores) on the crop it was given, points in the
crop's pixels, labels 1 for a click on the object and 0 for one off it; three masks, best first or not."""
import cv2
import numpy as np

from _core import lab

INSIDE = 0.75          # a mask with less of itself in the eye is not the eye's
IRIS_SHARE = (0.12, 0.72)   # the iris's share of the eye, between a pupil and the whole eye
WHITISH = 0.3          # a mask with more of it like the eye's white is not the iris
IRIS_SMALL, LASH_HEAVY, NO_WHITE = 0.15, 2.0, 0.03


def refs(L, eye):
    """The eye's own white and lash colours (CIELAB): the median of its whitest tenth (light and neutral) and of its
    darkest tenth."""
    W = L[..., 0] - 2 * np.hypot(L[..., 1], L[..., 2])
    white = eye & (W >= np.percentile(W[eye], 90))
    lash = eye & (L[..., 0] <= np.percentile(L[..., 0][eye], 10))
    return np.median(L[white], axis=0), np.median(L[lash], axis=0)


def deepest(m):
    """The point of mask m farthest inside it, (x, y)."""
    dt = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(dt)), dt.shape)
    return float(x), float(y)


def tones(L, eye):
    """(distance to the white, distance to the lashes, like the white) per pixel of the eye's crop."""
    wr, lr = refs(L, eye)
    d_w = np.linalg.norm(L - wr, axis=-1)
    d_l = np.linalg.norm(L - lr, axis=-1)
    return d_w, d_l, eye & (d_w < 0.5 * d_l) & (d_w < 15)


def iris_click(eye, d_w, d_l):
    """Where to click the iris: the deepest point of the largest piece of the eye's half least like its white or its
    lashes."""
    far = np.minimum(d_w, d_l)
    cand = eye & (far >= np.percentile(far[eye], 50))
    k, cc, st, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), connectivity=8)
    if k <= 1:
        return deepest(eye)
    return deepest(cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])))


def roundness(m):
    cnt, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnt, key=cv2.contourArea)
    return 4 * np.pi * cv2.contourArea(c) / max(1.0, cv2.arcLength(c, True)) ** 2


def pick_iris(masks, scores, eye, like_white):
    """Of the segmenter's masks, the most iris-like: mostly in the eye, neither a speck nor the whole eye, little of it
    like the white, scored by the segmenter and by its roundness."""
    best, bs = None, -1e9
    ne = max(1, int(eye.sum()))
    for mk, sc in zip(masks, scores):
        mk = np.asarray(mk) > 0
        if not mk.any():
            continue
        if ((mk & eye).sum() / mk.sum() < INSIDE or not IRIS_SHARE[0] <= (mk & eye).sum() / ne <= IRIS_SHARE[1]
                or (mk & like_white).sum() / mk.sum() > WHITISH):
            continue
        v = float(sc) + 0.5 * roundness(mk)
        if v > bs:
            best, bs = mk, v
    return best


def pick_white(masks, scores, eye, iris, d_w, d_l):
    """Of the segmenter's masks, the most white-like: mostly in the eye, not most of it, little of it the iris, nearer
    the eye's white than its lashes."""
    best, bs = None, -1e9
    ne = max(1, int(eye.sum()))
    for mk, sc in zip(masks, scores):
        mk = np.asarray(mk) > 0
        if not mk.any():
            continue
        on_iris = (mk & iris).sum() / mk.sum() if iris is not None else 0.0
        if ((mk & eye).sum() / mk.sum() < INSIDE or (mk & eye).sum() / ne > 0.6 or on_iris > WHITISH
                or np.median(d_w[mk]) >= np.median(d_l[mk])):
            continue
        if float(sc) > bs:
            best, bs = mk, float(sc)
    return best


def clicked(masks, scores, pos, neg, eye, avoid=None):
    """Of the segmenter's masks, the best scored that holds every click on the object and none off it, mostly in the
    eye (and, given `avoid`, little of it that)."""
    best, bs = None, -1e9
    for mk, sc in zip(masks, scores):
        mk = np.asarray(mk) > 0
        if not all(mk[int(y), int(x)] for x, y in pos) or any(mk[int(y), int(x)] for x, y in neg):
            continue
        if (mk & eye).sum() / max(1, mk.sum()) < 0.6:
            continue
        if avoid is not None and (mk & avoid).sum() / mk.sum() >= WHITISH:
            continue
        if float(sc) > bs:
            best, bs = mk, float(sc)
    return best


def split(predict, rgb, eye, iris_at=None, white_at=None, not_at=()):
    """(iris, white, lashes) masks of an eye: rgb its crop (uint8 or 0..1), eye its area there (a part segmentation's
    'eyes'). Clicks given in the crop's pixels (iris_at, white_at, not_at) replace the automatic ones; a click on the
    white is a click off the iris too. The iris is None when no mask fits."""
    rgb = np.asarray(rgb)
    L = lab(rgb.astype(np.float32) / 255.0 if rgb.dtype == np.uint8 else rgb)
    d_w, d_l, like_white = tones(L, eye)
    if iris_at:
        neg = list(not_at) + list(white_at or [])
        masks, scores = predict(np.array(list(iris_at) + neg, np.float32),
                                np.array([1] * len(iris_at) + [0] * len(neg), np.int32))
        iris = clicked(masks, scores, iris_at, neg, eye)
    else:
        masks, scores = predict(np.array([iris_click(eye, d_w, d_l)], np.float32), np.array([1], np.int32))
        iris = pick_iris(masks, scores, eye, like_white)
    white = np.zeros(eye.shape, bool)
    if white_at:
        for p in white_at:
            masks, scores = predict(np.array([p], np.float32), np.array([1], np.int32))
            w = clicked(masks, scores, [p], [], eye, avoid=iris)
            if w is not None:
                white |= w
    else:
        cand = like_white & (~iris if iris is not None else True)
        k, cc, st, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), connectivity=8)
        for c in sorted(range(1, k), key=lambda c_: -st[c_, cv2.CC_STAT_AREA])[:2]:
            if st[c, cv2.CC_STAT_AREA] < 0.02 * eye.sum():
                continue
            piece = cc == c
            masks, scores = predict(np.array([deepest(piece)], np.float32), np.array([1], np.int32))
            w = pick_white(masks, scores, eye, iris, d_w, d_l)
            white |= w if w is not None else piece
    white &= eye
    if iris is not None:
        iris = iris & ~white & eye
    lash = eye & ~(iris if iris is not None else np.zeros_like(eye)) & ~white & (d_l < d_w)
    return iris, white, lash


def doubts(iris, white, lash, eye):
    """Why an eye's split may be wrong (none: it looks right by its own proportions)."""
    ne = max(1, int(eye.sum()))
    ni = 0 if iris is None else int(iris.sum())
    why = []
    if iris is None:
        why.append("no iris found")
    elif ni < IRIS_SMALL * ne:
        why.append("the iris is small for the eye (a pupil or a catchlight taken?)")
    if iris is not None and lash.sum() > LASH_HEAVY * ni:
        why.append("the lashes outweigh the iris (its shaded upper half read as lashes?)")
    if white.sum() < NO_WHITE * ne:
        why.append("no white found (the white taken into the iris?)")
    return why
