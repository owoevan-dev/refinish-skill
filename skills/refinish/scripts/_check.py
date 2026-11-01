"""The checks on a finished picture: what a careful reviewer looks for first, measured. Each finding is a FAIL (a
mistake to fix before the picture is used) or a WARN (worth a look). The findings come with a box, so a review
picture can point at them.

  part map  P1 misfits (thick blobs much darker or lighter than their part: scripts/parts.py)              WARN
            P2 an iris read as hair or cloth (a style that moves the hair's colours moves the iris's too)   WARN
            M1 a patch inside a part that has another part's colour (a gold collar read as skin)            FAIL
  result    O1 a patch kept as drawn while the rest of its part changed (old hair colour left in a box)     FAIL
            O2 the white of an eye painted as skin                                                          FAIL
            O3 a dark line along an edge where the frame cuts the figure, which the source did not have     FAIL
            O4 a halo: the soft edge jumps in lightness from the figure more than in the source            WARN
            O5 an iris labelled hair or cloth and repainted (it comes out blotched)                       FAIL
            O6 a mass of pure black painted as its part (a keyhole read as gold)                           FAIL
  look      (look_checks: on every engine's own result, the prints, washes and duotones too)
            O7 a darker skin printed far lighter (every skin one pale colour); a light one far darker        FAIL/WARN
            O8 a box round the face's features: the face's tone stepping along a protected box's edge       FAIL
            O9 a dark part broken into patches (a wash's drift, a texture's mottle)                          WARN
  card      (recolour_checks: when a colour card recoloured parts, palette.py apply)
            RC1 a part's base colour off the card's (CIEDE2000 over 3 WARN, over 6 FAIL)                     WARN/FAIL
            RC2 a patch of the old colour left in a recoloured part (a line, a box, a fleck)               FAIL
            RC3 an iris off the card's hue, or the two eyes in different colours                           FAIL
            RC4 patches of a part the card left alone, inside one it recoloured and drawn like it         WARN
            RC5 pieces of a recoloured part far from it inside another, kept as drawn                    WARN
"""
import cv2
import numpy as np

from _core import lab, write_image
from _parts import misfits
from _style import kind_of

PAINTED_KINDS = ("skin", "hair", "cloth", "cloth-white", "cloth-dark", "sheer", "gloss", "metal")


def _patches(mask, min_area, scale_open=1, min_thick=0.0):
    """Coherent patches of a mask (specks opened away), as (box, area) pairs; with min_thick, only the patches thick
    enough to hold a disc of that radius (a misread garment or a misread neck is a blob; the gaps between strands of
    hair and the edges of a shine are thin)."""
    k = max(1, scale_open)
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    n, lab_, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    thick = cv2.distanceTransform(m, cv2.DIST_L2, 3) if min_thick > 0 else None
    out = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if a < min_area:
            continue
        if thick is not None and float(thick[y:y + h, x:x + w][lab_[y:y + h, x:x + w] == i].max()) < min_thick:
            continue
        out.append(([x, y, x + w, y + h], a))
    return out


def _hue_aware(px, centre):
    """Distance from a colour: hue and colourfulness for colourful pairs (a part's lit and shaded tones differ in
    lightness, a different material in hue), full colour distance for greys."""
    cp = np.hypot(px[:, 1], px[:, 2])
    cc = float(np.hypot(centre[1], centre[2]))
    dab = np.hypot(px[:, 1] - centre[1], px[:, 2] - centre[2])
    full = np.sqrt((px[:, 0] - centre[0]) ** 2 + dab ** 2)
    return np.where((cp > 10) & (cc > 10), dab, full)


def _clusters(px, k=4, seed=0):
    """A part's main source colours: k-means centres holding at least 8 % of its pixels."""
    if len(px) < 4 * k:
        return [np.median(px, axis=0)]
    rng = np.random.default_rng(seed)
    sub = px[rng.choice(len(px), min(len(px), 20000), replace=False)].astype(np.float32)
    w = np.array([0.6, 1, 1], np.float32)
    cv2.setRNGSeed(seed)                                # (k-means++ draws from OpenCV's generator)
    _, lbl, cen = cv2.kmeans(sub * w, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.5), 2,
                             cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=k) / len(sub)
    return [cen[i] / w for i in range(k) if share[i] >= 0.08]


def finish_map(subject, img, alpha, parts, U):
    """The part map a finish painted from, and the pixels it kept as drawn by rule: with a colour card, the map as
    _recolour.mend_parts mended it (an iris part's hair given back, a part's far pieces kept as drawn, the touches);
    without one, the map as it is."""
    if not subject.get("recolour"):
        return parts, np.zeros(parts.shape, bool)
    import _recolour as rc_
    mended, kept, _ = rc_.mend_parts(subject, img, alpha, parts, U, [None] + [kind_of(p) for p in subject["parts"]])
    return mended, kept


def part_map_checks(subject, img, alpha, parts, U, line, mended=None):
    """P1, P2, M1: the part map's likely mistakes, on the map the finish painted from (finish_map: with a card, a
    touch's patch is checked as the part it was given)."""
    found = []
    parts = (mended or finish_map(subject, img, alpha, parts, U))[0]
    for f in misfits(subject, img, alpha, parts, scale=U.s):
        found.append({"id": "P1", "level": "WARN", "part": f["part"], "box": f["box"], "area": f["area"],
                      "what": f"{f['what']} (a misfit: add a sample or a hint point)"})
    L = lab(img)
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = np.array([""] + [kind_of(p) for p in plist])
    skin = within & (kinds[parts] == "skin")
    skin_c = np.median(L[skin], axis=0) if skin.sum() > 50 else None
    # P2: the middle of an eye's box is its iris (the bangs and the lashes lie round it); labelled hair or cloth, it
    # changes with them under a style that moves their colours
    parts_p2 = parts
    for p in subject.get("protect", []):
        if "eye" not in p["name"] or skin_c is None:
            continue
        box, xyxy = _middle(p["box"])
        feat = within[box] & (np.linalg.norm(L[box] - skin_c, axis=2) > 14)
        if feat.sum() < 20:
            continue
        k = kinds[parts_p2[box][feat]]
        wrong = float(np.isin(k, ("hair", "cloth", "cloth-dark", "cloth-white", "sheer", "gloss")).mean())
        if wrong > 0.5:
            found.append({"id": "P2", "level": "WARN", "part": p["name"], "box": xyxy, "area": int(feat.sum()),
                          "what": f"{wrong:.0%} of the iris is labelled hair or cloth: a style that moves their "
                                  "colours moves it too (give the iris a part of kind eyes)"})
    # M1: a piece of another part labelled as this one, the way it shows: a patch of one colour inside the part, a
    # colour the part has nowhere else, that is the colour of a part it touches (a neck read as the gold collar beside
    # it, a waistband read as the jacket above the trousers, a lock of hair read as the jacket's collar). A part's own
    # shades recur over it (the red-orange shadows of orange hair); a misread piece is all in one place. The features
    # (eyes, a blush, small accessories) are no measure: a dark lock and a dark iris are near in colour
    min_area = max(30.0, U.area(30.0))
    core = within & ~line
    centres = {}
    for j, p in enumerate(plist, start=1):
        m = core & (parts == j)
        if kind_of(p) in PAINTED_KINDS and m.sum() >= max(200, 0.005 * within.sum()):
            centres[j] = _clusters(L[m])
    ring = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * U.k(3) + 1,) * 2)
    for j, p in enumerate(plist, start=1):
        if kind_of(p) not in PAINTED_KINDS or j not in centres:
            continue
        m = core & (parts == j)
        px = L[m]
        tone = np.full(m.shape, -1, np.int32)
        tone[m] = np.argmin(np.stack([_hue_aware(px, c) for c in centres[j]]), axis=0)
        for t in range(len(centres[j])):
            for box, a in _patches(tone == t, min_area, max(1, U.k(1)), min_thick=U.len(2.5)):
                x0, y0, x1, y1 = box
                sub = (tone[y0:y1, x0:x1] == t)
                c = np.median(L[y0:y1, x0:x1][sub], axis=0)
                elsewhere = m.copy()
                elsewhere[y0:y1, x0:x1] &= ~sub
                rest = L[elsewhere]                             # (empty when the patch is the whole part)
                if len(rest) and float((np.linalg.norm(rest - c, axis=1) < 8).mean()) >= 0.03:
                    continue                                    # a shade the part has all over
                patch = np.zeros(m.shape, np.uint8)
                patch[y0:y1, x0:x1] = sub
                touch = set(np.unique(parts[(cv2.dilate(patch, ring) > 0) & ~(patch > 0) & within]).tolist())
                # the same material in the same light: near in lightness too (a cardigan's dark inner fold has the hue
                # of navy hair beside it, not its darkness)
                other = [(min(float(np.linalg.norm(c - q)) for q in centres[o]), o) for o in centres
                         if o != j and o in touch]
                if not other:
                    continue
                dist, o = min(other)
                if dist <= 10:
                    # near-white and near-black are shared by too many materials (a trim, stitching, a highlight, the
                    # ink) for a patch of them to prove a misread part: a white trim on a jersey beside white shorts
                    neutral = float(np.hypot(c[1], c[2])) < 8 and (c[0] > 80 or c[0] < 22)
                    found.append({"id": "M1", "level": "WARN" if neutral else "FAIL", "part": p["name"], "box": box,
                                  "area": a,
                                  "what": f"a patch inside '{p['name']}' has the colour of '{plist[o - 1]['name']}' "
                                          f"beside it and none of its own: likely '{plist[o - 1]['name']}' read as "
                                          f"'{p['name']}' (move its region or add a hint point)" +
                                          (" - or its own white or black trim: look before moving it" if neutral
                                           else "")})
    return found


def _middle(b, frac=0.4):
    """The middle of a box, frac of its width and height: (slices, [x0, y0, x1, y1])."""
    x0, y0, x1, y1 = (int(v) for v in b)
    cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, frac * (x1 - x0) / 2, frac * (y1 - y0) / 2
    xyxy = [int(max(0, cx - hw)), int(max(0, cy - hh)), int(cx + hw) + 1, int(cy + hh) + 1]
    return (slice(xyxy[1], xyxy[3]), slice(xyxy[0], xyxy[2])), xyxy


def result_checks(subject, img, alpha, parts, out, out_alpha, U, line=None, mended=None):
    """O1 to O6: what went wrong in the finished picture, on the map the finish painted from (finish_map)."""
    found = []
    parts, kept_by_rule = mended or finish_map(subject, img, alpha, parts, U)
    Ls, Lo = lab(img), lab(out)
    within = (alpha > 0.5) & (out_alpha > 0.5)
    plist = subject["parts"]
    kinds = np.array([""] + [kind_of(p) for p in plist])
    min_area = max(30.0, U.area(8.0))
    dE = np.linalg.norm(Lo - Ls, axis=2)
    line = np.zeros(within.shape, bool) if line is None else line
    black = Ls[..., 0] < 15
    white = (Ls[..., 0] > 92) & (np.hypot(Ls[..., 1], Ls[..., 2]) < 6)
    # O1: a patch left as drawn inside a part whose other pixels all moved (a box that kept the old hair colour); the
    # lines, pure black and pure white (a shine) stay as drawn by design and do not count, nor what a card's finish
    # keeps as drawn by rule (a part's far pieces, which RC5 names; a touch's `keep`)
    for j, p in enumerate(plist, start=1):
        if kind_of(p) not in PAINTED_KINDS:
            continue
        m = within & (parts == j)
        if m.sum() < 500:
            continue
        free = m & ~line & ~black & ~white & ~kept_by_rule
        moved = float(np.median(dE[free])) if free.any() else 0.0
        if moved < 8:
            continue
        kept = free & (dE < 3)
        r = max(2, int(round(U.len(2.0))))
        ring_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        for box, a in _patches(kept, min_area, max(1, U.k(1)), min_thick=U.len(3.0)):
            # only a patch that shows: one whose colour stands apart from the part's new colour round it. Where the
            # flat paint happens to land on the source's own colour (a painted source's lit side) nothing was kept,
            # and the patch is the same colour as the paint round it
            x0, y0, x1, y1 = box
            pad = 2 * r
            ya, yb, xa, xb = max(0, y0 - pad), y1 + pad, max(0, x0 - pad), x1 + pad
            pm = kept[ya:yb, xa:xb]
            ring = (cv2.dilate(pm.astype(np.uint8), ring_k) > 0) & ~pm & m[ya:yb, xa:xb] & ~line[ya:yb, xa:xb]
            if pm.any() and ring.sum() > 20:
                inside, round_ = np.median(Lo[ya:yb, xa:xb][pm], axis=0), np.median(Lo[ya:yb, xa:xb][ring], axis=0)
                if np.linalg.norm(inside - round_) < 6:
                    continue
            found.append({"id": "O1", "level": "FAIL", "part": p["name"], "box": box, "area": a,
                          "what": f"a patch of '{p['name']}' kept as drawn while the rest moved by {moved:.0f}: "
                                  "check the protected boxes and the part's regions"})
    # O2: the white of an eye painted as skin
    skin = within & (kinds[parts] == "skin")
    if skin.sum() > 50:
        src_skin, out_skin = np.median(Ls[skin], axis=0), np.median(Lo[skin], axis=0)
        cs = float(np.hypot(src_skin[1], src_skin[2]))
        for p in subject.get("protect", []):
            if "eye" not in p["name"]:
                continue
            x0, y0, x1, y1 = (int(v) for v in p["box"])
            box = (slice(max(0, y0), y1), slice(max(0, x0), x1))
            C = np.hypot(Ls[box][..., 1], Ls[box][..., 2])
            white = within[box] & (Ls[box][..., 0] > 60) & (C < max(4.0, 0.6 * cs))
            if white.sum() < 20:
                continue
            as_skin = (np.linalg.norm(Lo[box] - out_skin, axis=2) < 8) & (dE[box] > 10) & white
            share = float(as_skin.sum() / white.sum())
            if share > 0.3:
                found.append({"id": "O2", "level": "FAIL", "part": p["name"], "box": [x0, y0, x1, y1],
                              "area": int(as_skin.sum()),
                              "what": f"{share:.0%} of the white of the {p['name']} is painted as skin: give the "
                                      "eye whites a part of kind eyes"})
    # O6: a mass of pure black painted as its part (a keyhole or a shadow mass read as gold or as skin, given the
    # part's colours). A style may lift all its blacks (a painted style has no pure black: its lines come out lifted
    # too), so the lift is read against the lift of the black lines; a mass lifted far more than them was painted
    mass = cv2.morphologyEx((black & within).astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * U.k(2) + 1,) * 2)) > 0
    black_lines = black & within & line & ~mass
    black_point = float(np.median(Lo[black_lines][:, 0] - Ls[black_lines][:, 0])) if black_lines.sum() > 200 else 0.0
    lifted = mass & (Lo[..., 0] - Ls[..., 0] - max(0.0, black_point) > 30)
    rec = (subject.get("recolour") or {}).get("parts", {})
    if rec and lifted.any():
        # a colour card that makes a dark part light: a part that was black all over (black tights, black hair) is
        # painted in the card's colours, its black with them; in a part that was not, a black painted no lighter
        # than the card's darkest colour for the part (+10) is the card's own shadow. Only a black mass in a part of
        # another colour, painted lighter than that, is still a misread part (a keyhole in gold)
        import _colour as C_
        floor = np.full(lifted.shape, -1.0, np.float32)
        for j, q in enumerate(plist, start=1):
            r_ = rec.get(q["name"])
            m_ = (parts == j) & within
            if r_ and m_.any():
                if float(np.median(Ls[m_][:, 0])) < 40:
                    floor[m_] = 101.0
                else:
                    floor[m_] = 10.0 + min(lab(C_.parse_hex(r_[s]).astype(np.float32).reshape(1, 1, 3))[0, 0, 0]
                                           for s in ("deep", "shadow", "base") if s in r_)
        lifted &= ~((floor >= 0) & (Lo[..., 0] <= floor))
    for box, a in _patches(lifted, min_area, max(1, U.k(1))):
        x0, y0, x1, y1 = box
        sub = lifted[y0:y1, x0:x1]
        names = [plist[j - 1]["name"] for j in np.unique(parts[y0:y1, x0:x1][sub]) if j > 0]
        found.append({"id": "O6", "level": "FAIL", "part": ",".join(names) or "-", "box": box, "area": a,
                      "what": f"a mass of pure black painted as '{','.join(names)}' (lightness "
                              f"{np.median(Ls[y0:y1, x0:x1][sub][:, 0]):.0f} -> {np.median(Lo[y0:y1, x0:x1][sub][:, 0]):.0f}): "
                              "give the black its own part of kind accessory"})
    # O5: an iris repainted as hair or cloth: the middle of an eye's box, labelled hair or cloth, changed from its
    # drawing (an iris is kept as drawn, or moved by the features' own palette as a part of kind eyes; painted with
    # the hair's colour model it comes out blotched)
    if skin.sum() > 50:
        for p in subject.get("protect", []):
            if "eye" not in p["name"]:
                continue
            box, xyxy = _middle(p["box"])
            iris = within[box] & (np.linalg.norm(Ls[box] - src_skin, axis=2) > 14)
            if iris.sum() < 20:
                continue
            other = iris & np.isin(kinds[parts[box]], ("hair", "cloth", "cloth-dark", "cloth-white", "sheer", "gloss"))
            if other.sum() < 0.5 * iris.sum():
                continue
            # blotched: a good share of it moved, where an iris kept as drawn hardly moves at all
            moved = float((dE[box][other] > 12).mean())
            if moved >= 0.25:
                found.append({"id": "O5", "level": "FAIL", "part": p["name"], "box": xyxy, "area": int(other.sum()),
                              "what": f"the iris of the {p['name']} is labelled hair or cloth and was repainted "
                                      f"({moved:.0%} of it moved): give the iris a part of kind eyes"})
    # O3: a dark line along an edge the frame cuts
    h, w = alpha.shape
    band = max(2, int(round(U.len(3.0))))
    sides = {"top": (slice(0, band), slice(None)), "bottom": (slice(h - band, h), slice(None)),
             "left": (slice(None), slice(0, band)), "right": (slice(None), slice(w - band, w))}
    inside = {"top": (slice(band, 2 * band), slice(None)), "bottom": (slice(h - 2 * band, h - band), slice(None)),
              "left": (slice(None), slice(band, 2 * band)), "right": (slice(None), slice(w - 2 * band, w - band))}
    rec_names = set((subject.get("recolour") or {}).get("parts", {}))
    rec_m = np.isin(parts, [j for j, p in enumerate(subject["parts"], start=1) if p["name"] in rec_names])
    for name, sl in sides.items():
        m = within[sl]
        edge = {"top": alpha[0], "bottom": alpha[-1], "left": alpha[:, 0], "right": alpha[:, -1]}[name] > 0.5
        if edge.mean() < 0.05 or m.sum() < 50:
            continue
        ref = Ls[sl][..., 0].copy()
        if rec_m.any() and min(h, w) > 4 * band:
            # a colour card's part made dark is dark to the frame's edge: there the line is measured against the
            # result's own colour just inside the band (with the step the source itself had there)
            r_ = rec_m[sl]
            ref[r_] = (Lo[inside[name]][..., 0] + Ls[sl][..., 0] - Ls[inside[name]][..., 0])[r_]
        darker = (ref - Lo[sl][..., 0] > 25) & m
        share = float(darker.sum() / m.sum())
        if share > 0.3:
            ys, xs = np.nonzero(m)
            oy = 0 if name != "bottom" else h - band
            ox = 0 if name != "right" else w - band
            found.append({"id": "O3", "level": "FAIL", "part": "-",
                          "box": [int(xs.min() + ox), int(ys.min() + oy), int(xs.max() + ox), int(ys.max() + oy)],
                          "area": int(darker.sum()),
                          "what": f"a dark line along the {name} edge, where the frame cuts the figure ({share:.0%} "
                                  "of that edge): an outline drawn where the figure goes on beyond the frame"})
    # O4: a halo, the soft edge much lighter or darker than the figure inside it, more than in the source
    soft = (out_alpha > 0.05) & (out_alpha < 0.95)
    if soft.sum() > 100:
        inner = cv2.erode(within.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        dist, idx = cv2.distanceTransformWithLabels((~inner).astype(np.uint8), cv2.DIST_L2, 5,
                                                    labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(inner)
        lut_y = np.zeros(idx.max() + 1, np.int64)
        lut_x = np.zeros(idx.max() + 1, np.int64)
        lut_y[idx[ys, xs]], lut_x[idx[ys, xs]] = ys, xs
        sy, sx = np.nonzero(soft)
        ny, nx = lut_y[idx[sy, sx]], lut_x[idx[sy, sx]]
        jump_o = np.abs(Lo[sy, sx, 0] - Lo[ny, nx, 0])
        jump_s = np.abs(Ls[sy, sx, 0] - Ls[ny, nx, 0])
        if rec_m.any():
            # beside a colour card's part the source's step means little (its outline is now a dark shade of a new
            # colour, light hair round a dark line): there only a soft edge lighter than the part is a halo
            r_ = rec_m[ny, nx]
            jump_o = np.where(r_, Lo[sy, sx, 0] - Lo[ny, nx, 0], jump_o)
            jump_s = np.where(r_, Ls[sy, sx, 0] - Ls[ny, nx, 0], jump_s)
        more = float((jump_o > 30).mean() - (jump_s > 30).mean())
        if more > 0.15:
            found.append({"id": "O4", "level": "WARN", "part": "-", "box": [int(sx.min()), int(sy.min()),
                                                                          int(sx.max()), int(sy.max())],
                          "area": int(soft.sum()), "what": f"a halo: {more:.0%} more of the soft edge jumps in "
                                                           "lightness than in the source"})
    return found


def _frame(out, alpha_shape):
    """A result in its source's frame: a grown picture (a sticker's border, a neon glow) cut back to its middle, a
    smaller one (a pixel sprite) enlarged to it."""
    h, w = alpha_shape
    if out.shape[:2] == (h, w):
        return out
    if out.shape[0] >= h and out.shape[1] >= w:
        py, px = (out.shape[0] - h) // 2, (out.shape[1] - w) // 2
        return out[py:py + h, px:px + w]
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_NEAREST)


def _smooth_in(L, m, sig):
    num = cv2.GaussianBlur(np.where(m, L, 0).astype(np.float32), (0, 0), sig)
    den = cv2.GaussianBlur(m.astype(np.float32), (0, 0), sig)
    return num / np.maximum(den, 1e-3)


SKIN_DARK = 62.0          # O7: a face darker than this in the source is a tan to a deep skin
SKIN_LIFT = 25.0          # how much lighter such a face may come out (a brown skin printed paper-white lifts about 50)
SKIN_DROP = 30.0          # how much darker than the figure a light face may come out
SEAM_STEP, SEAM_SHARE = 12.0, 0.4
MOTTLE = 6.0
NO_SKIN_CHECK = ("neon", "pencil")          # the look sinks or empties every fill by design
NO_MOTTLE_CHECK = ("neon", "pixel", "tone")  # dark ground, flat pixel blocks, solid black with white lights: by design


def look_checks(subject, img, alpha, parts, out, U, engine=None):
    """O7 to O9, on the result itself, for every engine (the prints, washes and drawings too, whose other checks read
    their cel base): what a style's own look did to the figure.

      O7 the skin repainted far lighter or darker than the rest of the figure moved (every skin printed one colour)  FAIL
      O8 a box round the face's features: the face's tone stepping along a protected box's straight edge           FAIL
      O9 a dark part broken into patches (a wash's drift, a texture's mottle) far more than in the source          WARN
    """
    found = []
    h, w = alpha.shape
    out = _frame(out, (h, w))
    Ls, Lo = lab(img)[..., 0], lab(np.clip(out, 0, 1).astype(np.float32))[..., 0]
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = np.array([""] + [kind_of(p) for p in plist])
    pk = kinds[parts]
    skin = within & (pk == "skin")
    # read at a screen's scale, so dots and hatching count as the tone they print, not as steps
    sig = max(1.0, U.len(1.5))
    So, Ss = _smooth_in(Lo, within, sig), _smooth_in(Ls, within, sig)
    # O7: a darker skin printed far lighter (every skin painted the period's pale), or a light one far darker than the
    # rest of the figure went
    from _core import ellipse_mask
    face = skin & (ellipse_mask(h, w, subject.get("focal", [])) > 0.5)
    if face.sum() < 300:
        face = skin
    if face.sum() >= 300 and engine not in NO_SKIN_CHECK:
        # read wider still: a pop-art screen's dots are 9 u apart, and a face's tone is what they average to
        # (within the skin: dark hair round a small face must not darken it)
        sig7 = max(2.0, U.len(5.0))
        So7, Ss7 = _smooth_in(Lo, skin, sig7), _smooth_in(Ls, skin, sig7)
        s_face, o_face = float(np.median(Ss7[face])), float(np.median(So7[face]))
        lift = o_face - s_face
        rel = lift - (float(np.median(So[within])) - float(np.median(Ss[within])))
        ys, xs = np.nonzero(face)
        box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        if s_face < SKIN_DARK and lift > SKIN_LIFT and rel > 0.8 * SKIN_LIFT:
            found.append({"id": "O7", "level": "FAIL", "part": "skin", "box": box, "area": int(face.sum()),
                          "what": f"a darker skin printed far lighter ({s_face:.0f} -> {o_face:.0f}): the style paints "
                                  "the skin a colour of its own instead of the figure's"})
        elif s_face >= SKIN_DARK and rel < -SKIN_DROP:
            found.append({"id": "O7", "level": "WARN", "part": "skin", "box": box, "area": int(face.sum()),
                          "what": f"a light skin printed far darker than the rest of the figure ({s_face:.0f} -> "
                                  f"{o_face:.0f}): look at the face"})
    # O8: a step along a protected box's edge on the skin, which the source does not have
    d = max(2, int(round(U.len(1.5))))
    for p in (subject.get("protect", []) if engine != "pixel" else []):      # (a pixel block's edge is no seam)
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        x0, y0, x1, y1 = max(d, x0), max(d, y0), min(w - d - 1, x1), min(h - d - 1, y1)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        ins, outs = [], []
        for y in range(y0, y1):                                   # left and right edges
            ins += [(y, x0 + d), (y, x1 - d)]
            outs += [(y, x0 - d), (y, x1 + d)]
        for x in range(x0, x1):                                   # top and bottom edges
            ins += [(y0 + d, x), (y1 - d, x)]
            outs += [(y0 - d, x), (y1 + d, x)]
        iy, ix = np.array(ins).T
        oy, ox = np.array(outs).T
        ok = skin[iy, ix] & skin[oy, ox]
        if ok.sum() < 20:
            continue
        step = np.abs(So[iy, ix] - So[oy, ox]) - np.abs(Ss[iy, ix] - Ss[oy, ox])
        share = float((step[ok] > SEAM_STEP).mean())
        if share > SEAM_SHARE:
            found.append({"id": "O8", "level": "FAIL", "part": p.get("name", "-"), "box": [x0, y0, x1, y1],
                          "area": int(ok.sum()),
                          "what": f"a box round the {p.get('name', 'feature')}: the face's tone steps along {share:.0%} "
                                  "of the box's edge (a feature kept or inked by a fixed level against a skin "
                                  "repainted round it)"})
    # O9: a dark part's broad lightness spread, result against source
    sig2 = max(1.5, U.len(2.0))
    for j, p in enumerate(plist, start=1):
        if kinds[j] in ("hair", "eyes", "accessory", "skin", "") or engine in NO_MOTTLE_CHECK:
            continue
        m = within & (parts == j)
        if m.sum() < U.area(400) or float(np.median(Ls[m])) >= 30:
            continue
        inner = cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=max(1, int(U.len(2.0)))) > 0
        if inner.sum() < 200:
            continue
        spread = float(np.std(_smooth_in(Lo, m, sig2)[inner])) - float(np.std(_smooth_in(Ls, m, sig2)[inner]))
        if spread > MOTTLE:
            ys, xs = np.nonzero(inner)
            found.append({"id": "O9", "level": "WARN", "part": p["name"],
                          "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())], "area": int(inner.sum()),
                          "what": f"'{p['name']}' is broken into patches: its broad lightness spread grew by "
                                  f"{spread:.0f} over the source's (a texture or a wash's drift on a dark part)"})
    return found


def _hue_deg(f):
    return np.degrees(np.arctan2(f[..., 2], f[..., 1])) % 360


def recolour_checks(subject, img, alpha, parts, out, U):
    """A colour card's parts on the result. RC1: the part's base colour, as the centre of its lit tone (the cluster of
    its interior colours nearest the card's base), against the card's base, by CIEDE2000. RC2: the old colour left, in
    patches: pixels still near the part's own old hue (within 30 degrees) and far (45) from every colour the card gives
    it; for a part that was near-neutral (a white shirt made pink), pixels still near-neutral and light. A line in a
    neighbour's new colour along a small part's edge is neither. RC3: the irises against the card's iris hue, and the
    two eyes against each other. RC4: a left-alone part's patches inside a recoloured one (_strays_inside). RC5: a
    recoloured part's far pieces inside another, kept as drawn (_recolour.mend_parts)."""
    import _colour as C
    rec = (subject.get("recolour") or {}).get("parts", {})
    if not rec:
        return []
    found = []
    within = alpha > 0.5
    f = lab(out)
    fs = lab(img)
    chroma = np.hypot(f[..., 1], f[..., 2])
    hue = _hue_deg(f)
    k = 2 * max(1, int(round(U.len(1.0)))) + 1
    iris = []
    import _recolour as rc_
    kinds = [None] + [kind_of(q) for q in subject["parts"]]
    # the part map as the finish mended it for the card: the hair an iris part took given back, the pieces joined to a
    # recoloured part by colour alone kept as drawn (RC5 names them)
    parts, kept, pieces = rc_.mend_parts(subject, img, alpha, parts, U, kinds)
    skin = within & np.isin(parts, [j for j, kk in enumerate(kinds) if j > 0 and kk == "skin"])
    lost = [list(b) for b in rc_.mislabelled_irises(subject, fs, within, parts, kinds, skin)]
    # (an eye part's pixels that can be the iris's: not the skin or the white of the eye it was drawn wide over; and
    # what a touch gave an iris)
    names = [q["name"] for q in subject["parts"]]
    touched_eyes = np.zeros(alpha.shape, bool)
    for m_, t in rc_.touch_masks(subject, img, alpha, U):
        if "as" in t and kinds[names.index(t["as"]) + 1] == "eyes":
            touched_eyes |= m_
    iris_src = rc_.iris_like(fs, np.median(fs[skin], axis=0) if skin.sum() > 50 else None) | touched_eyes
    in_box = rc_.box_fade(subject, *alpha.shape) > 0
    # the source's lines, where the finish lays its own ink (a brown ink over hair made black is the style's, not the
    # part's colour): the checks measure the fills
    from _guard import dark_lines
    ink = cv2.dilate(dark_lines(img, within, U).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    lost_box = np.zeros(alpha.shape, bool)
    for x0, y0, x1, y1 in lost:
        lost_box[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    for j, p in enumerate(subject["parts"], start=1):
        r = rec.get(p["name"])
        if r is None or "gradient" in r:
            continue
        m = (parts == j) & within & ~kept
        inner = cv2.erode(m.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
        if p.get("kind") != "eyes":
            inner &= ~ink
        if inner.sum() < 60:
            continue
        card = {s: lab(C.parse_hex(r[s]).astype(np.float32).reshape(1, 1, 3))[0, 0]
                for s in ("base", "shadow", "deep", "highlight") if s in r}
        px = f[inner]
        # RC1: the lit tone's centre (a few k-means steps started at the card's own colours, a cluster per tone)
        cents = np.array(list(card.values()), np.float32)
        for _ in range(6):
            lab_ = np.argmin(np.linalg.norm(px[:, None, :] - cents[None], axis=2), axis=1)
            cents = np.array([px[lab_ == i].mean(0) if (lab_ == i).any() else cents[i] for i in range(len(cents))])
        bi = list(card).index("base")
        ys, xs = np.nonzero(inner)
        box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
        if p.get("kind") != "eyes" and float((lab_ == bi).mean()) > 0.03:
            de = float(C.ciede2000(cents[bi], card["base"]))
            if de > 3.0:
                found.append({"id": "RC1", "level": "FAIL" if de > 6.0 else "WARN", "part": p["name"], "box": box,
                              "area": int(inner.sum()),
                              "what": f"'{p['name']}' is painted {de:.1f} (CIEDE2000) off the card's base {r['base']}"})
        # RC2: the old colour, wherever it lies in the part's fills outside the protected boxes (inside them the
        # features are kept as drawn, and what the part map gave this part only there with them; RC3 measures the
        # irises). The darkest pixels, below L* 25, are ink: their colour is the style's (a brown ink over brown hair
        # made violet)
        # (an eyes part: its iris alone, as the finish recolours it, _recolour.iris_core; an iris a segmenter split,
        # whole)
        core = None
        if p.get("kind") == "eyes":
            core = m if p.get("exact") else rc_.iris_core(subject, m & iris_src) | (m & touched_eyes)
        m2 = (m & ~in_box & ~ink if core is None else core & ~lost_box) & (f[..., 0] >= 25)
        old = np.median(fs[inner], axis=0)
        old_c = float(np.hypot(old[1], old[2]))
        if old_c >= 8:
            far = np.ones(m2.shape, bool)
            for c in card.values():
                cc = float(np.hypot(c[1], c[2]))
                far &= (chroma > cc + 14) if cc < 8 else (np.abs((hue - _hue_deg(c[None])[0] + 180) % 360 - 180) > 45)
            near_old = np.abs((hue - _hue_deg(old[None])[0] + 180) % 360 - 180) < 30
            resid = m2 & far & near_old & (chroma > 8)
        elif float(np.hypot(card["base"][1], card["base"][2])) >= 12:
            resid = m2 & (chroma < 4) & (f[..., 0] > 45)      # a white made coloured: white left where colour belongs
        else:
            resid = np.zeros(m2.shape, bool)
        patches = _patches(resid, U.area(4.0), max(1, int(round(U.len(0.4)))))
        share = resid.sum() / max(1, m2.sum())
        if patches and share > 0.005:
            box2, _ = max(patches, key=lambda t: t[1])
            found.append({"id": "RC2", "level": "FAIL", "part": p["name"], "box": box2, "area": int(resid.sum()),
                          "what": f"{100 * share:.1f}% of '{p['name']}' keeps a colour the card does not give it "
                                  "(the old colour: a line, a box, a fleck)"})
        if core is not None:
            sel = core & (chroma > 8)
            for b in subject.get("protect", []):
                if "eye" not in b.get("name", ""):
                    continue
                x0, y0, x1, y1 = (int(v) for v in b["box"])
                s_ = np.zeros_like(sel)
                s_[y0:y1, x0:x1] = sel[y0:y1, x0:x1]
                if s_.sum() > 20:
                    iris.append((np.median(f[s_], axis=0), [x0, y0, x1, y1], p["name"], card["base"]))
    # an eye whose iris the part map gave to the hair or the clothes is left as drawn by the finish: say why
    why = (" (its iris is labelled hair or cloth, so the eye was left as drawn: give the iris a part of kind eyes, "
           "as P2 says)")
    for med, box, name, cb in iris:
        off = abs((_hue_deg(med[None])[0] - _hue_deg(cb[None])[0] + 180) % 360 - 180)
        if np.hypot(cb[1], cb[2]) >= 8 and off > 25:
            found.append({"id": "RC3", "level": "FAIL", "part": name, "box": box, "area": 0,
                          "what": f"the iris in this eye is {off:.0f} degrees of hue off the card's"
                                  + (why if box in lost else "")})
    if len(iris) >= 2:
        d = float(C.ciede2000(iris[0][0], iris[1][0]))
        if d > 10:
            odd = next((t for t in iris if t[1] in lost), iris[1])
            found.append({"id": "RC3", "level": "FAIL", "part": odd[2], "box": odd[1], "area": 0,
                          "what": f"the two eyes differ by {d:.1f} (CIEDE2000): one iris is not recoloured like the "
                                  "other" + (why if odd[1] in lost else " (part of it labelled skin or eye-white?)")})
    found += _strays_inside(subject, fs, f, within, parts, U, rec, ink, in_box)
    # RC5: the pieces kept as drawn (mend_parts), by the part they were joined to and the part they lie in
    seen = {}
    for a, b, box, n in pieces:
        if n < U.area(4.0):
            continue
        v = seen.setdefault((a, b), box + [0])
        v[:4] = [min(v[0], box[0]), min(v[1], box[1]), max(v[2], box[2]), max(v[3], box[3])]
        v[4] += n
    for (a, b), v in seen.items():
        found.append({"id": "RC5", "level": "WARN", "part": a, "box": v[:4], "area": v[4],
                      "what": f"pieces of '{a}' far from it inside '{b}' were kept as drawn (joined to '{a}' by "
                              f"colour alone, as a gold ornament to blonde hair): if they are '{a}' (a strap cut off by "
                              f"an arm), give '{a}' \"pieces\": \"paint\" on the card"})
    return found


def _strays_inside(subject, fs, f, within, parts, U, rec, ink, in_box):
    """RC4: a patch of a part the card left alone, lying inside a part it recoloured and drawn like that part in the
    source: most likely that part's own, which the part map gave to its neighbour (a cream tee's light folds read as
    the pale skin beside it). In the source's colours it never showed; now it keeps the old look while all round it
    changed. A patch of the left-alone part's own colour (skin seen between strands of dark hair) is not one."""
    rec_idx = [j for j, p in enumerate(subject["parts"], start=1) if p["name"] in rec]
    if not rec_idx:
        return []
    h, w = within.shape
    fill = within & ~ink & ~in_box
    med_src, med_out = {}, {}

    def medians(k):
        if k not in med_src:
            m = (parts == k) & fill
            med_src[k] = np.median(fs[m], axis=0) if m.sum() > 50 else None
            med_out[k] = np.median(f[m], axis=0) if m.sum() > 50 else None
        return med_src[k], med_out[k]

    hits = {}
    for j, p in enumerate(subject["parts"], start=1):
        if p["name"] in rec or kind_of(p) == "eyes":
            continue
        n, lbl, st, _ = cv2.connectedComponentsWithStats(((parts == j) & fill).astype(np.uint8), connectivity=8)
        if n <= 2:
            continue
        main = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in st[i])
            if i == main or area < U.area(4.0):
                continue
            y0, y1, x0, x1 = max(0, y - 3), min(h, y + bh + 3), max(0, x - 3), min(w, x + bw + 3)
            c = lbl[y0:y1, x0:x1] == i
            ring = ((cv2.dilate(c.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~c & within[y0:y1, x0:x1]
                    & ~ink[y0:y1, x0:x1])
            around = parts[y0:y1, x0:x1][ring]
            in_rec = np.isin(around, rec_idx)
            if len(around) < 10 or in_rec.mean() < 0.6:
                continue
            k = int(np.bincount(around[in_rec]).argmax())
            ks, ko = medians(k)
            if ks is None:
                continue
            if (np.linalg.norm(np.median(fs[y0:y1, x0:x1][c], axis=0) - ks) <= 15
                    and np.linalg.norm(np.median(f[y0:y1, x0:x1][c], axis=0) - ko) > 15):
                hb = hits.setdefault((p["name"], subject["parts"][k - 1]["name"]), [x, y, x + bw, y + bh, 0])
                hb[:4] = [min(hb[0], x), min(hb[1], y), max(hb[2], x + bw), max(hb[3], y + bh)]
                hb[4] += area
    return [{"id": "RC4", "level": "WARN", "part": a, "box": v[:4], "area": v[4],
             "what": f"patches labelled '{a}' inside '{b}' keep the old look while '{b}' changed, and were drawn like "
                     f"'{b}': if they are {b}, give them to it (a hint point); if not, name '{a}' on the card"}
            for (a, b), v in hits.items()]


def verdict(found):
    return "fail" if any(f["level"] == "FAIL" for f in found) else "warn" if found else "pass"


def review(out_rgb, out_alpha, found, path):
    """The finished picture with each finding boxed and numbered (red FAIL, orange WARN), and a key."""
    bg = np.array([228, 228, 228], np.float32) / 255.0
    pic = out_rgb * out_alpha[..., None] + bg * (1 - out_alpha[..., None])
    vis = cv2.cvtColor((np.clip(pic, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    for i, f in enumerate(found, start=1):
        x0, y0, x1, y1 = f["box"]
        col = (40, 40, 230) if f["level"] == "FAIL" else (40, 160, 240)
        cv2.rectangle(vis, (x0 - 3, y0 - 3), (x1 + 3, y1 + 3), col, 3)
        cv2.putText(vis, str(i), (x0, max(14, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
    s = min(1.0, 1800.0 / vis.shape[0])
    vis = cv2.resize(vis, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    key = np.full((vis.shape[0], 520, 3), 255, np.uint8)
    for i, f in enumerate(found[:60], start=1):
        cv2.putText(key, f"{i} {f['id']} {f['level']} {f['part']}"[:60], (8, 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (30, 30, 30), 1)
    write_image(str(path), np.hstack([vis, key]), [cv2.IMWRITE_JPEG_QUALITY, 88])
