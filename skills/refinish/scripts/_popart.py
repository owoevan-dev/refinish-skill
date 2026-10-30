"""Pop art in the comic printing it borrowed from: heavy black lines, flat process inks (red, yellow, blue and black on
white paper), and every tint printed as Ben-Day dots, an even grid of dots of one ink whose size gives the tint.

Each tone of each part (its base, shadow and light in the cel base) is matched to the nearest overprint of the inks,
each ink at a few coverages (solid, or dots), so a light skin prints as red and yellow dots on white, an orange as
yellow with red dots, a navy as solid blue with black dots; at most two inks are dotted in one tone, their dots side by
side. The coverages are chosen per tone, so a flat area prints in even dots. A skin the inks cannot reach (a tan, a
brown) is printed in a spot ink of its own colour with its shading in black dots. The eyes and the mouth are painted
flat, no dots over them.

Style keys, section `pop`: `inks` (name to RGB 0..255: red, yellow, blue, black), `paper` (RGB), `cell` (u, the dot
grid's spacing, 9), `angles` (per ink, degrees; one grid, 45), `levels` (the coverages a dotted ink may print
at, besides 0 and 1; 0.18, 0.3, 0.42, so the dots stay round and apart),
`line_grow` (u, how much the lines are thickened, 1.0), `outline` (u, the figure's outer line, 3.0), `spot_above`
(how far, in delta E, the nearest overprint may be from a skin before it takes a spot ink, 10)."""
import itertools

import cv2
import numpy as np

import _flat
import _halftone as ht
from _core import lab_px, protect_mask, rgb
from _lines import find_lines

INKS = {"red": [226, 38, 44], "yellow": [252, 220, 38], "blue": [36, 92, 186], "black": [24, 22, 26]}
ANGLES = {"red": 45.0, "yellow": 45.0, "blue": 45.0, "black": 45.0}    # one grid for every ink...
OFFSETS = {"red": (0.0, 0.0), "yellow": (0.5, 0.5), "blue": (0.5, 0.0), "black": (0.0, 0.5)}   # ...each ink's dots
# set between the others' (in cells), so two dotted inks print side by side and mix by eye, the way a comic's flat
# tints did


def _lin(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def lab_px_y(c):
    """The relative luminance (linear) of one Lab colour."""
    L = float(c[0])
    return ((L + 16) / 116) ** 3 if L > 8 else L / 903.3


def mixes(inks, paper, levels):
    """Every overprint of the inks at the given coverages: (coverages, Lab). Inks multiply in linear light: each one
    passes its own colour where it is printed (a coverage c of it lets 1 - c of the light through untouched)."""
    names = list(inks)
    T = {n: _lin(np.array(inks[n]) / 255) / np.maximum(_lin(np.array(paper) / 255), 1e-4) for n in names}
    out = []
    for cs in itertools.product(*[[0.0] + list(levels) + [1.0]] * len(names)):
        if sum(0.0 < c < 1.0 for c in cs) > 2:
            continue                                        # (two inks in dots at most, their dots side by side)
        if names.count("black") and cs[names.index("black")] not in (0.0, 1.0) and sum(cs) > cs[names.index("black")]:
            continue                                        # (black dots only on their own)
        col = _lin(np.array(paper) / 255)
        for n, c in zip(names, cs):
            col = col * (1 - c + c * T[n])
        out.append((dict(zip(names, cs)), lab_px(_srgb(col))))
    return out


def run(subject, style, cel, alpha, parts, U, seed=7):
    ps = style.get("pop", {})
    inks = {**INKS, **ps.get("inks", {})}
    paper = ps.get("paper", [250, 247, 240])
    levels = ps.get("levels", [0.18, 0.3, 0.42])           # (dots that stay round and apart)
    cell = max(3.0, U.len(ps.get("cell", 9.0)))
    angles = {**ANGLES, **ps.get("angles", {})}
    h, w = alpha.shape
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    table = mixes(inks, paper, levels)
    labs = np.array([c for _, c in table], np.float32)

    def nearest(c):
        d = labs - np.asarray(c, np.float32)
        d[:, 0] *= 0.7                                      # (a print's lightness steps are coarse; its hues count)
        return table[int(np.argmin((d ** 2).sum(1)))][0]

    cover = {n: np.zeros((h, w), np.float32) for n in inks}
    # a skin the process inks cannot reach (a tan or a brown: two dotted inks at most print either a pale pink or a
    # near black) is printed in a spot ink of its own colour, as the comics did a colour off the process palette, its
    # shading in black dots over it; a light skin keeps the classic red and yellow dots
    spot = np.zeros((h, w, 3), np.float32)
    spot_a = np.zeros((h, w), np.float32)
    black_tr = float(np.mean(_lin(np.array(inks["black"]) / 255) / np.maximum(_lin(np.array(paper) / 255), 1e-4)))
    steps = [0.0] + list(levels)

    def match_de(c):
        d = labs - np.asarray(c, np.float32)
        return float(np.sqrt((d ** 2).sum(1)).min())

    for lay in _flat.layers(cel, parts, within, kinds):
        base_rgb = None
        if lay["kind"] == "skin" and match_de(lay["base_lab"]) > ps.get("spot_above", 10.0):
            base_rgb = _lin(rgb(np.array(lay["base_lab"], np.float32).reshape(1, 1, 3))[0, 0])
            Yb = float(lab_px_y(lay["base_lab"]))
        for i, col in enumerate(lay["colours"]):
            m = lay["mask"] & (lay["tone"] == i)
            if not m.any():
                continue
            if base_rgb is not None:
                spot[m], spot_a[m] = base_rgb, 1.0
                # the tone's darkening as black dots over the spot ink: the coverage that prints the tone's lightness
                c_b = float(np.clip((1 - lab_px_y(col) / max(Yb, 1e-4)) / max(1e-4, 1 - black_tr), 0, 1))
                cover["black"][m] = min(steps, key=lambda s: abs(s - c_b)) if c_b < 0.5 else levels[-1]
                continue
            mix = nearest(col)
            for n, c in mix.items():
                cover[n][m] = c
    # print: each ink through its own dot screen, solid where it is solid, the paper multiplied by every ink laid
    paper_lin = _lin(np.array(paper) / 255)
    out = np.ones((h, w, 3), np.float64) * paper_lin
    out = out * (1 - spot_a[..., None]) + spot.astype(np.float64) * spot_a[..., None]
    for n, c in cover.items():
        if not c.any():
            continue
        ox, oy = OFFSETS.get(n, (0.0, 0.0))
        T = ht.threshold((h, w), cell, angles.get(n, 45.0), "dot", seed=seed, origin=(ox * cell, oy * cell))
        cov = np.where(c >= 0.999, 1.0, np.where(c <= 0.001, 0.0, ht.screen(c, T, cell)))
        tr = _lin(np.array(inks[n]) / 255) / np.maximum(paper_lin, 1e-4)
        out = out * (1 - cov[..., None] + cov[..., None] * tr)
    out = _srgb(out).astype(np.float32)
    # the features (the eyes, the mouth) painted flat in their own colours, no dots over them: a face under dots the
    # size of an iris cannot be read; only the features, not their boxes, or the box's skin shows as a patch
    skin_m = np.isin(parts, [j for j, k in enumerate(kinds) if k == "skin"])
    prot = protect_mask(subject, h, w, cel, skin_m, parts=parts)[..., None]
    out = out * (1 - prot) + cel * prot
    # the lines, black and heavy, and the figure's outline
    ink = np.array(inks["black"], np.float32) / 255
    L_line = find_lines(cel, subject.get("upscaled", 1))
    line = (L_line > 0.3) & within
    g = max(1, int(round(U.len(ps.get("line_grow", 1.0)))))
    line = cv2.dilate(line.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * g + 1, 2 * g + 1))) > 0
    d = cv2.distanceTransform(within.astype(np.uint8), cv2.DIST_L2, 3)
    outline = within & (d <= U.len(ps.get("outline", 3.0)))
    k = np.clip(cv2.GaussianBlur((line | outline).astype(np.float32), (0, 0), 0.7), 0, 1)[..., None]
    out = out * (1 - k) + ink * k
    return np.clip(out, 0, 1), {"inks": {n: [int(v) for v in c] for n, c in inks.items()}}
