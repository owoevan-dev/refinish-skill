"""The parts of a subject, as the engines need them: colour families sampled from the picture (each pixel to the
nearest family, the way a compositor pulls mattes), the parts that share a family told apart by where they may be
(the navy of the skirt from the navy of the hair), and each pixel only ever weighing the families allowed where it
lies. A subject written by scripts/auto_parts.py names a region map instead: each part owns the regions listed."""
import cv2
import numpy as np

from _core import die, lab
from _style import subject_path

LIGHT_KINDS = ("skin", "cloth-white", "cloth")
DARK_KINDS = ("hair", "cloth-dark", "sheer", "gloss")


def place(p, h, w):
    """Where a part may be: its polygons, or everywhere when it has none."""
    if not ("poly" in p or "polys" in p):
        return np.ones((h, w), bool)
    m = np.zeros((h, w), np.uint8)
    for poly in (p["polys"] if "polys" in p else [p["poly"]]):
        cv2.fillPoly(m, [np.int32(poly)], 1)
    return m > 0


def placed(p):
    return "poly" in p or "polys" in p


def sample_colours(L, pts):
    out = []
    for x, y in pts:
        x, y = int(x), int(y)
        out.append(np.median(L[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3), axis=0))
    return out


def families(subject, img, within, max_dist=40.0, min_area=20, smooth=2.0):
    """Each pixel to the nearest colour family among those with a part allowed where it lies; then the family most
    of its neighbourhood has (shading speckle and line pixels join the region around them). A lock of hair beside the
    cheek, grey-violet where the light catches it, may be nearest in colour to the tights; the tights may not be
    there, so it goes to the hair instead of falling through to the skin around it."""
    h, w = within.shape
    L = lab(img)
    names = list(subject["families"])
    best = np.full((h, w), np.inf, np.float32)
    idx = np.full((h, w), -1, np.int32)
    for ci, name in enumerate(names):
        mine = [p for p in subject["parts"] if p["family"] == name]
        if not mine or any(not placed(p) for p in mine):
            allowed = np.ones((h, w), bool)
        else:
            allowed = np.zeros((h, w), bool)
            for p in mine:
                allowed |= place(p, h, w)
        for c in sample_colours(L, subject["families"][name]):
            d = np.sqrt(((L - c) ** 2).sum(axis=2))
            upd = allowed & (d < best)
            best[upd] = d[upd]
            idx[upd] = ci
    idx[(best > max_dist) | ~within] = -1
    votes = np.stack([cv2.GaussianBlur((idx == ci).astype(np.float32), (0, 0), smooth) for ci in range(len(names))])
    voted = np.where((votes.max(0) > 0.05) & within, votes.argmax(0), -1)
    fam = np.full((h, w), -1, np.int32)
    for ci in range(len(names)):
        m = (voted == ci).astype(np.uint8)
        n2, lab2, stats, _ = cv2.connectedComponentsWithStats(m)
        keep = np.zeros(n2, bool)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
        fam[keep[lab2]] = ci
    return names, fam


def nearest_label(labels, todo):
    """Fill the todo pixels with the nearest labelled pixel's label."""
    if not todo.any():
        return labels
    _, near = cv2.distanceTransformWithLabels((labels <= 0).astype(np.uint8), cv2.DIST_L2, 5,
                                              labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(labels > 0)
    lut = np.zeros(near.max() + 1, labels.dtype)
    lut[near[ys, xs]] = labels[ys, xs]
    labels = labels.copy()
    labels[todo] = lut[near[todo]]
    return labels


def region_map(subject, shape):
    """The region map a subject names (each pixel's region number), checked against the picture's size."""
    reg = cv2.imread(str(subject_path(subject, subject["regions"])), cv2.IMREAD_UNCHANGED)
    if reg is None:
        die(f"cannot read the region map {subject['regions']}; run scripts/auto_parts.py again")
    if reg.shape != shape:
        die(f"the region map {subject['regions']} is {reg.shape[1]}x{reg.shape[0]}, the picture "
            f"{shape[1]}x{shape[0]}; run scripts/auto_parts.py again")
    return reg.astype(np.int32)


def part_map_from_regions(subject, alpha):
    """0 outside the figure, then the parts in the order of the subject file: each part takes the regions in its
    "regions" list, a region in no list goes to the nearest part, and a part's polygons take every pixel inside them
    (to carve out what the regions do not separate)."""
    h, w = alpha.shape
    within = alpha > 0.5
    reg = region_map(subject, (h, w))
    lut = np.zeros(int(reg.max()) + 1, np.uint8)
    for j, p in enumerate(subject["parts"], start=1):
        for i in p.get("regions", []):
            if 0 < int(i) < len(lut):
                lut[int(i)] = j
    parts = lut[reg]
    parts[~within] = 0
    parts = nearest_label(parts, (parts == 0) & within)
    for j, p in enumerate(subject["parts"], start=1):
        if placed(p):
            parts[place(p, h, w) & within] = j
    parts[~within] = 0
    return parts


def part_map(subject, img, alpha, reach=30):
    """0 outside the figure, then the parts in the order of the subject file."""
    if "regions" in subject:
        return part_map_from_regions(subject, alpha)
    h, w = alpha.shape
    within = alpha > 0.5
    names, fam = families(subject, img, within)
    # what no family took (speckle, line pixels between families) goes to the nearest family
    todo = (fam < 0) & within
    if todo.any():
        f1 = nearest_label(fam + 1, todo) - 1
        fam = np.where(todo, f1, fam)
    parts = np.zeros((h, w), np.uint8)
    # placed parts first, in file order (a later one wins where they overlap), then each unplaced part takes the rest
    # of its family (except a family whose parts are only where they were placed)
    for j, p in enumerate(subject["parts"], start=1):
        if placed(p):
            parts[(fam == names.index(p["family"])) & place(p, h, w)] = j
    only = [names.index(q["family"]) for q in subject["parts"] if q.get("only_placed")]
    for j, p in enumerate(subject["parts"], start=1):
        if not placed(p):
            parts[(fam == names.index(p["family"])) & (parts == 0) & ~np.isin(fam, only)] = j
    # what no part took goes to the part, among those allowed where it lies and found close by, whose family's
    # samples (lit and shaded tones both) are nearest in colour; the rest to the nearest part in space
    left = (parts == 0) & within
    if left.any():
        L = lab(img)
        disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * reach + 1, 2 * reach + 1))
        best = np.full((h, w), np.inf, np.float32)
        choice = np.zeros((h, w), np.uint8)
        for j, p in enumerate(subject["parts"], start=1):
            own = parts == j
            if own.sum() < 50:
                continue
            d = np.min([np.sqrt(((L - c) ** 2).sum(axis=2)) for c in sample_colours(L, subject["families"][p["family"]])],
                       axis=0)
            d[cv2.dilate(own.astype(np.uint8), disk) == 0] = np.inf
            d[~place(p, h, w)] = np.inf
            upd = left & (d < best)
            best[upd] = d[upd]
            choice[upd] = j
        ok = left & np.isfinite(best)
        parts[ok] = choice[ok]
    left = (parts == 0) & within
    parts = nearest_label(parts, left)
    # an exclusive part owns its polygons outright, whatever the colours there (a dark iris the colour of the dark hair
    # around it)
    for j, p in enumerate(subject["parts"], start=1):
        if p.get("exclusive") and placed(p):
            parts[place(p, h, w) & within] = j
    parts[~within] = 0
    return parts


def kind_of(p):
    return p.get("kind", p.get("as", "cloth"))


def misfits(subject, img, alpha, parts, scale=1.0, open_px=9, step=30.0):
    """The part map's likely mistakes: thick blobs much darker than the rest of their part (a lock of navy hair
    labelled as skin) and large blobs much lighter (larger than a shine on hair or patent leather), each part judged
    against its own median lightness, so light hair and dark hair are both judged fairly. Areas are at the reference
    scale (a figure about 3000 px tall) and scaled by `scale`. Returns a list of findings."""
    L = lab(img)[..., 0]
    opaque = alpha > 0.8
    k = max(3, int(round(open_px * scale)) | 1)
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    found = []
    for j, p in enumerate(subject["parts"], start=1):
        if kind_of(p) in ("eyes", "accessory"):
            continue
        m = opaque & (parts == j)
        if m.sum() < 500:
            continue
        med = float(np.median(L[m]))
        for what, mask, min_area in (("much darker than its part", m & (L < med - step), 200 * scale * scale),
                                     ("much lighter than its part", m & (L > med + step), 1500 * scale * scale)):
            thick = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, disk)
            n, lb, st, _ = cv2.connectedComponentsWithStats(thick)
            for i in range(1, n):
                if st[i, cv2.CC_STAT_AREA] >= min_area:
                    x, y, ww, hh, area = (int(v) for v in st[i])
                    found.append({"what": what, "part": p["name"], "box": [x, y, x + ww, y + hh], "area": area})
    return found
