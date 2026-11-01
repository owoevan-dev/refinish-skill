"""Recolouring by part, the pieces the finishes share.

- Which parts a card recoloured (the subject's `recolour` record, written by palette.py apply).
- The transfer of a part's own rendering to the card's colours, as a compositor maps a cel to a colour design with a
  gradient map (colorama): the part's lightness mapped monotonically onto the card's knots (shadow, base, highlight),
  the colour at each lightness taken from the knots, a little of the part's own colour variation kept, all in Oklab,
  and gamut-mapped (_colour.py). Used for the irises in a protected box (phase 1) and for whole parts (keep-finish).
- Which lines belong to the hair: in anime the hair lies over the face, so the line between hair and skin is the
  hair's, and a strand drawn as a line across the face is hair too; recoloured hair takes those lines along
  (色トレス: a line is a dark shade of the colour it bounds)."""
import cv2
import numpy as np

import _colour as C
from _core import box_ramp, lab

# a recoloured part's small piece (at most PIECE_SHARE of the part's body), this far from the body (u) and lying inside
# one other part, is not the part's: a shirt's cuff inside a jacket's sleeve, the skirt under a crossing arm are large
PIECE_FAR = 40.0
PIECE_INSIDE = 0.85
PIECE_SHARE = 0.05


def recoloured(subject):
    """{part name: its record} for the parts a card recoloured (empty when the subject has no card)."""
    return (subject.get("recolour") or {}).get("parts", {})


def part_index(subject, names):
    return [j for j, p in enumerate(subject["parts"], start=1) if p["name"] in names]


def mend_parts(subject, img, alpha, parts, U, kinds):
    """The part map's mistakes a recolour would paint, mended for it (a finish in the same colours hides them):
    - an eyes part's pixels that are the hair over the eye (the dark hair round a dark iris read as iris): the hair's
      colour, joined to the hair outside the eye's box without crossing a line. They go to the hair;
    - a recoloured part's small pieces (PIECE_SHARE of its body at most) far from its body (PIECE_FAR u), lying inside
      one other part (PIECE_INSIDE of the ring round them): joined to the part by colour alone (a book's gold
      ornaments read as blonde hair, a jacket's silver buckles as silver hair, a shadow under the chin as dark hair, a
      blush as pink hair). They are kept as drawn: painted in the part's new colour they would show it where it is not.
    - last, the touches an agent wrote after looking at a result (palette.py apply --touch), over the rules above: the
      pixels a touch reaches (touch_masks) go to the part it names (`as`), or are kept as drawn (`keep`), or are left
      out of every part to take the touch's own colour in the finish (`to`).
    The finish and the checks mend the same way (the source's lines are read the guard's way, _guard.dark_lines).
    Returns (parts, kept: the pixels kept as drawn, pieces: [(part, part it lies in, box, pixels)])."""
    from _guard import dark_lines
    rec = recoloured(subject)
    h, w = parts.shape
    within = alpha > 0.5
    parts = parts.copy()
    kept = np.zeros((h, w), bool)
    pieces = []
    if not rec and not (subject.get("recolour") or {}).get("touch"):
        return parts, kept, pieces
    names = [p["name"] for p in subject["parts"]]
    line = dark_lines(img, within, U)
    Lab = lab(img)
    boxes = box_fade(subject, h, w) > 0
    hair_idx = [j for j in range(1, len(kinds)) if kinds[j] == "hair"]
    eye_idx = [j for j in part_index(subject, rec) if kinds[j] == "eyes"]
    hair_out = np.isin(parts, hair_idx) & within & ~line & ~boxes
    if eye_idx and hair_out.sum() > 200:
        cand = (np.isin(parts, eye_idx) & within & ~line
                & (np.linalg.norm(Lab - np.median(Lab[hair_out], axis=0), axis=-1) < 15))
        if cand.any():
            fill = (np.isin(parts, hair_idx) & within & ~line) | cand
            _, lbl = cv2.connectedComponents(fill.astype(np.uint8), connectivity=4)
            out = np.unique(lbl[hair_out])
            moved = cand & np.isin(lbl, out[out > 0])
            if moved.any():
                ring = (cv2.dilate(moved.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & np.isin(parts, hair_idx)
                parts[moved] = int(np.bincount(parts[ring]).argmax()) if ring.any() else hair_idx[0]
    far = U.len(PIECE_FAR)
    for j in part_index(subject, rec):
        if kinds[j] == "eyes" or rec[names[j - 1]].get("pieces", "keep") == "paint":
            continue
        n, lbl, st, _ = cv2.connectedComponentsWithStats(((parts == j) & within).astype(np.uint8), connectivity=8)
        if n <= 2:
            continue
        main = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        d_main = cv2.distanceTransform((lbl != main).astype(np.uint8), cv2.DIST_L2, 5)
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in st[i])
            if i == main or area > PIECE_SHARE * st[main, cv2.CC_STAT_AREA]:
                continue
            y0, y1, x0, x1 = max(0, y - 3), min(h, y + bh + 3), max(0, x - 3), min(w, x + bw + 3)
            c = lbl[y0:y1, x0:x1] == i
            if d_main[y0:y1, x0:x1][c].min() < far:
                continue
            ring = (cv2.dilate(c.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~c
            around = parts[y0:y1, x0:x1][ring]
            if len(around) < 10:
                continue
            others = around[(around != j) & (around > 0)]
            if not len(others):
                continue
            k = int(np.bincount(others).argmax())
            if (others == k).sum() >= PIECE_INSIDE * len(around):
                kept[y0:y1, x0:x1] |= c
                pieces.append((names[j - 1], names[k - 1], [x, y, x + bw, y + bh], area))
    # the touches last (palette.py apply --touch): the agent's own word, over every rule above
    for m, t in touch_masks(subject, img, alpha, U, line, Lab):
        if "as" in t:
            if t["as"] not in names:                   # (a subject rebuilt from this one may not have the part)
                continue
            parts[m] = names.index(t["as"]) + 1
            kept &= ~m
            pieces = [pc for pc in pieces if not m[pc[2][1]:pc[2][3], pc[2][0]:pc[2][2]].any()]
        else:
            kept |= m
    return parts, kept, pieces


# a touch's reach: the colours within TOUCH_TOL (CIELAB) of the colour at its point; a point on a line, with no box,
# grows within TOUCH_REACH (u) of itself
TOUCH_TOL = 12.0
TOUCH_REACH = 20.0


def touch_masks(subject, img, alpha, U, line=None, Lab=None):
    """The touches on the card's record (palette.py apply --touch), each with the pixels it reaches: from each of its
    points, the fill round it, the pixels within its `tol` (CIELAB) of the colour at the point, joined to the point
    without crossing a line (the guard's dark_lines), inside its box when it has one. A point on a line (a dark thing
    the line finder reads as ink) grows over the lines as well, inside its box or within TOUCH_REACH u of itself.
    [(mask, touch)], in the record's order."""
    touches = (subject.get("recolour") or {}).get("touch", [])
    if not touches:
        return []
    h, w = alpha.shape
    within = alpha > 0.5
    if line is None:
        from _guard import dark_lines
        line = dark_lines(img, within, U)
    if Lab is None:
        Lab = lab(img)
    out = []
    for t in touches:
        m = np.zeros((h, w), bool)
        for x, y in t["at"]:
            x, y = int(round(x)), int(round(y))
            if not (0 <= x < w and 0 <= y < h) or not within[y, x]:
                continue
            if "box" in t:
                x0, y0, x1, y1 = (int(v) for v in t["box"])
            else:
                r = 10 ** 6 if not line[y, x] else int(round(U.len(TOUCH_REACH)))
                x0, y0, x1, y1 = x - r, y - r, x + r + 1, y + r + 1
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
            if not (x0 <= x < x1 and y0 <= y < y1):
                m[y, x] = True                         # (a point outside its own box reaches itself alone)
                continue
            # the work inside the box or the reach alone, not over the whole picture
            free = within[y0:y1, x0:x1] & (True if line[y, x] else ~line[y0:y1, x0:x1])
            Lw, yy, xx = Lab[y0:y1, x0:x1], y - y0, x - x0
            win = (slice(max(0, yy - 2), yy + 3), slice(max(0, xx - 2), xx + 3))
            ref = np.median(Lw[win][free[win]], axis=0) if free[win].any() else Lab[y, x]
            cand = free & (np.linalg.norm(Lw - ref, axis=-1) < t.get("tol", TOUCH_TOL))
            cand[yy, xx] = True
            _, lbl = cv2.connectedComponents(cand.astype(np.uint8), connectivity=4)
            m[y0:y1, x0:x1] |= lbl == lbl[yy, xx]
        out.append((m, t))
    return out


# where each card colour sits among a part's own tones: a colour design's part is mostly lit, with a shadow over a
# fifth of it, a second shadow in its deepest corners and a highlight on its brightest few
ANCHOR = {"deep": 4.0, "shadow": 18.0, "base": 62.0, "highlight": 97.0}
TIE = 0.01                                             # Oklab L: knots anchored closer than this on a part are one
# the most of a card's part its highlight covers in a cel finish
HIGHLIGHT_SHARE = 0.1


def knots(rec, slots=("deep", "shadow", "base", "highlight")):
    """A part's card colours as (percentile anchor, Oklab) knots, darkest first."""
    return [(ANCHOR[s], C.srgb_to_oklab(C.parse_hex(rec[s]))) for s in slots if s in rec]


def iris_like(Lab, skin_lab):
    """The pixels that can be an iris's: not within 10 (CIELAB) of the skin's colour, and not near-neutral while as
    light as the skin or lighter (the white of the eye, a catchlight). An eye part drawn a little wide (a polygon round
    the iris taking in some of the white and the skin) takes a card's iris colour on its iris alone; the rest of it
    stays as drawn. Lab: the source in CIELAB; skin_lab: the skin's median colour."""
    if skin_lab is None:
        return np.ones(Lab.shape[:2], bool)
    near_skin = np.linalg.norm(Lab - skin_lab, axis=-1) < 10
    white = (Lab[..., 0] >= skin_lab[0] - 5) & (np.hypot(Lab[..., 1], Lab[..., 2]) < 6)
    return ~near_skin & ~white


# an iris is the eye's thick round mass: an eyes part's strips narrower than the iris's own inscribed radius are not
# the iris (the upper lash line, a lash's tail, a strand of the hair over the eye joined to it by colour), nor is
# anything beyond the eye's protected box widened by IRIS_PAD of its size
IRIS_OPEN = 0.5
IRIS_PAD = 0.25


def iris_core(subject, m):
    """The iris in an eyes part's iris-like pixels m: per eye box (widened by IRIS_PAD), what a disc of IRIS_OPEN x the
    iris's inscribed radius fits in (a morphological opening), with two pixels of its edge back (the opening rounds the
    corners where a lash meets the iris). The iris's shape takes in its catchlights and pale patches, the holes in m:
    they stay as drawn, but they are the iris's, and without them a lash line looks as thick as the iris round them. A
    dark iris and the lashes and strands round it are one colour, so the part map often joins them; painted in the
    card's iris colour they come out as coloured lash lines and strokes beside the eye. No eye box: m as it is."""
    h, w = m.shape
    boxes = [b["box"] for b in subject.get("protect", []) if "eye" in b.get("name", "")]
    if not boxes:
        return m
    out = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in ([int(v) for v in b] for b in boxes):
        px, py = int(IRIS_PAD * (x1 - x0)), int(IRIS_PAD * (y1 - y0))
        sl = (slice(max(0, y0 - py), max(0, min(h, y1 + py))), slice(max(0, x0 - px), max(0, min(w, x1 + px))))
        mb = m[sl]
        if mb.sum() < 20:
            continue
        shape = np.pad(mb.astype(np.uint8), 1)
        cv2.floodFill(shape, None, (0, 0), 2)
        shape = (mb | (shape[1:-1, 1:-1] == 0)).astype(np.uint8)
        r = max(1, int(round(IRIS_OPEN * float(cv2.distanceTransform(shape, cv2.DIST_L2, 5).max()))))
        core = cv2.morphologyEx(shape, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2))
        out[sl] |= (cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0) & mb
    return out


def transfer(src_rgb, mask, kn, keep=0.3, white_keep=False):
    """src_rgb's pixels under mask carried onto the knots ((anchor, Oklab), darkest first): a monotonic
    piecewise-linear map from the part's own lightness at each knot's anchor percentile to the knot's lightness,
    the colour at the mapped lightness interpolated between the knots, `keep` of the part's own colour variation
    (its deviation from its median a, b) added back. Beyond the outer knots the lightness goes on toward black and
    white at the slope the room allows, between 1 and 4 (a pupil stays dark; a white turned black does not burst into
    light flecks from its last few points of lightness). Knots anchored on one lightness (a flat fill, a source of a
    few flat tones) count once: the one anchored nearest the middle of the pixels there, so a flat fill takes the
    base. white_keep: a specular white (an eye's catchlight) stays white; True for every pixel, or a mask over the
    masked pixels for those only. Returns the new sRGB values of the masked pixels, gamut-mapped."""
    ok = C.srgb_to_oklab(src_rgb[mask])
    if len(ok) == 0 or not kn:
        return src_rgb[mask]
    Lsrc = ok[:, 0]
    cols = np.array([k[1] for k in kn])
    kL = np.maximum.accumulate(np.clip(cols[:, 0], 0, 1))
    qs = np.percentile(Lsrc, [k[0] for k in kn])
    srt, use, i = np.sort(Lsrc), [], 0
    while i < len(kn):
        j = i
        while j + 1 < len(kn) and qs[j + 1] - qs[i] < TIE:
            j += 1
        if j > i:
            mid = 50.0 * (np.searchsorted(srt, qs[i] - TIE) + np.searchsorted(srt, qs[j] + TIE, side="right")) / len(srt)
            use.append(min(range(i, j + 1), key=lambda q: abs(kn[q][0] - mid)))
        else:
            use.append(i)
        i = j + 1
    qs, kU = qs[use], kL[use]
    qs = np.maximum.accumulate(qs + np.arange(len(qs)) * 1e-6)
    if len(qs) > 1:
        Lnew = np.interp(Lsrc, qs, kU)
    else:
        Lnew = kU[0] + (Lsrc - qs[0])
    lo, hi = Lsrc < qs[0], Lsrc > qs[-1]
    s_lo = np.clip(kU[0] / max(qs[0], 1e-3), 1.0, 4.0)
    s_hi = np.clip((1 - kU[-1]) / max(1 - qs[-1], 1e-3), 1.0, 4.0)
    Lnew[lo] = kU[0] - (qs[0] - Lsrc[lo]) * s_lo
    Lnew[hi] = kU[-1] + (Lsrc[hi] - qs[-1]) * s_hi
    Lnew = np.clip(Lnew, 0.0, 1.0)
    # the colour at that lightness: between the knots (the outer ones beyond them)
    n = len(kn)
    t = np.interp(Lnew, kL, np.arange(n)) if n > 1 else np.zeros_like(Lnew)
    i0 = np.clip(np.floor(t).astype(int), 0, n - 1)
    i1 = np.clip(i0 + 1, 0, n - 1)
    w = (t - i0)[:, None]
    ab = cols[i0, 1:] * (1 - w) + cols[i1, 1:] * w
    ab = ab + keep * (ok[:, 1:] - np.median(ok[:, 1:], axis=0))
    res = C.oklab_to_srgb(np.concatenate([Lnew[:, None], ab], 1))
    if isinstance(white_keep, np.ndarray) or white_keep:
        spec = (Lsrc > 0.92) & (np.hypot(ok[:, 1], ok[:, 2]) < 0.04)
        if isinstance(white_keep, np.ndarray):
            spec &= white_keep
        res[spec] = src_rgb[mask][spec]
    return res.astype(np.float32)


def nearest_colour(paint, mask):
    """For every pixel, the colour of the nearest pixel of mask in paint (h, w, 3)."""
    if not mask.any():
        return paint.copy()
    dist, lbl = cv2.distanceTransformWithLabels((~mask).astype(np.uint8), cv2.DIST_L2, 5,
                                                labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(~((~mask).astype(bool)))                  # the zero pixels in raster order: label k is the k-th
    lut = np.zeros((lbl.max() + 1, 3), np.float32)
    lut[1:len(ys) + 1] = paint[ys, xs]
    return lut[lbl]


def hair_lines(L_line, hair, protect, U, boundary=2.0, reach=8.0):
    """The line pixels that are the hair's: within `boundary` u of the hair (the line between hair and skin), and the
    strands drawn as lines across the face, which run on from the hair: runs of line within `reach` u of it that touch
    it. Lines in the protected boxes (lashes, brows) are the face's."""
    on = L_line > 0.3
    if not hair.any() or not on.any():
        return np.zeros(L_line.shape, bool)
    hb = cv2.dilate(hair.astype(np.uint8), cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * max(1, int(round(U.len(boundary)))) + 1,) * 2)) > 0
    near = cv2.dilate(hair.astype(np.uint8), cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * max(1, int(round(U.len(reach)))) + 1,) * 2)) > 0
    cand = on & near & (protect < 0.5)
    n, lbl = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
    touch = np.unique(lbl[cand & (cv2.dilate(hair.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)])
    strands = np.isin(lbl, touch[touch > 0])
    return (on & hb & (protect < 0.5)) | strands


def box_fade(subject, h, w):
    """The protected boxes as weights: 1 inside, fading over each box's outer eighth, as the boxes keep the features."""
    out = np.zeros((h, w), np.float32)
    for b in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in b["box"])
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1] = np.maximum(out[y0:y1, x0:x1], box_ramp(x1 - x0, y1 - y0))
    return out


def reaching_in(subject, parts, idx, fill, Lv):
    """The pixels of parts idx inside the protected boxes that are those parts reaching in from outside (bangs over an
    eye, a clip beside it): their fill joined to the part's fill outside the boxes, not across a line, nor across ink
    darker than any of the part's own tones there (a lash is drawn darker than the hair it touches). What the part map
    labelled a part only inside a box (the white of an eye read as the shirt, a lash or a catchlight read as hair) is
    the feature's own drawing, and stays as drawn. Lv: the picture's lightness (CIELAB L*)."""
    h, w = parts.shape
    boxes = box_fade(subject, h, w) > 0
    got = np.zeros((h, w), bool)
    for j in idx:
        pm = (parts == j) & fill
        if not (pm & boxes).any() or not (pm & ~boxes).any():
            continue
        pm &= ~boxes | (Lv >= np.percentile(Lv[pm & ~boxes], 1) - 2.0)
        _, lbl = cv2.connectedComponents(pm.astype(np.uint8), connectivity=4)
        out = np.unique(lbl[pm & ~boxes])
        got |= np.isin(lbl, out[out > 0]) & boxes
    return got


def mislabelled_irises(subject, Lab, within, parts, kinds, skin):
    """The eyes whose iris the part map gave to the hair or the clothes, as the checks read them (P2, O5): the middle of
    the eye's protected box, its pixels unlike the skin, mostly labelled hair or cloth. Their boxes [x0, y0, x1, y1].
    Such an iris cannot be told from the lashes and the hair round it, so a card leaves that eye as drawn: half an iris
    recoloured is worse than none (RC3 reports it, with the fix: give the iris a part of kind eyes)."""
    out = []
    if skin.sum() <= 50:
        return out
    skin_c = np.median(Lab[skin], axis=0)
    wrong_kinds = ("hair", "cloth", "cloth-dark", "cloth-white", "sheer", "gloss")
    kk = np.array([""] + list(kinds[1:]))
    for b in subject.get("protect", []):
        if "eye" not in b["name"]:
            continue
        x0, y0, x1, y1 = (int(v) for v in b["box"])
        cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, 0.4 * (x1 - x0) / 2, 0.4 * (y1 - y0) / 2
        sl = (slice(int(max(0, cy - hh)), int(cy + hh) + 1), slice(int(max(0, cx - hw)), int(cx + hw) + 1))
        feat = within[sl] & (np.linalg.norm(Lab[sl] - skin_c, axis=2) > 14)
        if feat.sum() < 20:
            continue
        if (feat & np.isin(kk[parts[sl]], wrong_kinds)).sum() > 0.5 * feat.sum():
            out.append([x0, y0, x1, y1])
    return out


def slivers(parts, idx, within, is_line, U):
    """Thin pieces of parts idx (narrower than about a third of a unit) lying between a line and another part's fill:
    the part map drew the boundary a pixel or two beyond the line, so they belong to the area on their side of it (a
    strip of the hair along the cardigan's edge, outside the line between them). {part index: mask}. A strand drawn
    between two lines touches no other fill, and stays."""
    r = max(1, int(round(U.len(0.35))))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2)
    near_line = cv2.dilate(is_line.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    fills = within & ~is_line
    out = {}
    for j in idx:
        fp = (parts == j) & fills
        thin = fp & ~(cv2.morphologyEx(fp.astype(np.uint8), cv2.MORPH_OPEN, k) > 0)
        if not thin.any():
            continue
        other = fills & (parts != j) & (parts > 0)
        sl = thin & near_line & (cv2.dilate(other.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        if sl.any():
            out[j] = sl
    return out


def ink_lightness(img, L_line, within):
    """The picture's own ink: the Oklab lightness of its strongest lines (0.2 when it has too few)."""
    m = (L_line > 0.6) & within
    return float(np.median(C.srgb_to_oklab(img[m])[:, 0])) if m.sum() > 50 else 0.2


def fill_round(img, L_line, within, sigma):
    """The colour of the fill round each pixel: a blur over the figure that leaves out the lines and what lies outside
    the figure (a cut-out's soft edge takes the fill just inside it)."""
    wgt = np.clip(1 - L_line * 2.2, 0, 1) * within
    num = cv2.GaussianBlur(img * wgt[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(wgt.astype(np.float32), (0, 0), sigma)[..., None]
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), img).astype(np.float32)


def ink_over(src, fill_src, fill_new, mask, ink_L):
    """The pixels under mask (lines, a cut-out's soft edge) redrawn over the new fills with the ink they held in the
    source: their darkness below their own fill, as a share of the picture's ink below it, laid over the new fill toward
    a line as dark as the picture's ink (or a step below a darker fill: a black shirt's outline stays darker than the
    shirt), in the new fill's hue with the chroma fading toward the line. A dark outline round dark hair stays an
    outline round white hair, the line between two recoloured parts stays a line, and a fill's own soft edge stays the
    fill's new colour."""
    s, f, n = (C.srgb_to_oklab(x[mask]) for x in (src, fill_src, fill_new))
    a = np.clip((f[:, 0] - s[:, 0]) / np.maximum(f[:, 0] - ink_L, 0.05), 0.0, 1.0)
    Lk = np.minimum(ink_L, 0.6 * n[:, 0])
    L = n[:, 0] - a * (n[:, 0] - Lk)
    ab = n[:, 1:] * (1 - 0.7 * a)[:, None]
    return C.oklab_to_srgb(np.concatenate([L[:, None], ab], 1)).astype(np.float32)


def fringe(out, img, alpha, within, rec_mask, is_line, fill_src, ink_L):
    """The cut-out's soft edge (0 < alpha <= 0.5, outside what the finish paints) beside a recoloured part, redrawn over
    the part's new colour with the ink it held (ink_over): an outline's soft edge stays dark, a fill's takes the new
    colour, and the old colour shows nowhere as a thin rim."""
    soft = (alpha > 0.01) & ~within
    if not soft.any() or not rec_mask.any():
        return out
    d_rec = cv2.distanceTransform((~rec_mask).astype(np.uint8), cv2.DIST_L2, 5)
    d_oth = cv2.distanceTransform((~(within & ~rec_mask)).astype(np.uint8), cv2.DIST_L2, 5)
    sel = soft & (d_rec <= d_oth)
    if sel.any():
        out = out.copy()
        fill = rec_mask & ~is_line
        out[sel] = ink_over(img, fill_src, nearest_colour(out, fill if fill.any() else rec_mask), sel, ink_L)
    return out
