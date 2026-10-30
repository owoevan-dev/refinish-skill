"""The woodblock engine: a figure printed the way an Edo colour woodblock print (nishiki-e) was, from a cel finish of
it (the style's `base`).

  - the key block (墨板): the lines carved crisp, printed in sumi at an even weight, the outline closed;
  - one colour block per part, in the pigment of the period nearest its colour (indigo, Prussian blue, safflower
    red, red lead, orpiment yellow, a green of indigo over yellow, purple, ochre brown, sumi grey); a printed
    pigment is transparent, so its strength (how much of it the block carries) sets the lightness and the paper
    shows through it; a light skin stays near the paper, as in the prints, a darker one keeps its own value;
  - shadow is not painted: a part's shadow becomes bokashi (ぼかし), a gradation wiped onto the block, darker along
    the part's shaded side and fading into its colour;
  - the block's own surface: the wood's grain in the larger flats, the baren's mottle, a colour printed a hair off
    the key block (registration), on washi.

Style keys, section `woodblock`: `pigments` (name -> Lab, replacing the period's), `skin` (a light skin's strength),
`pale_above` (the skin lightness above which a skin is printed near the paper, 74; darker skins blend to their own),
`bokashi` (0..1, how dark the gradation goes), `grain` (the woodgrain's strength), `offset` (u), `line_width` (u),
`paper` (a sheet kind).
"""
import cv2
import numpy as np

import _flat
import _lines
import _texture as tx
from _core import lab, rgb

PIGMENTS = {                                   # approximate Lab of each pigment at full strength on washi
    # sumi as the prints have it: the darkest 2 % of five Edo prints (CC0 museum scans) lie at L 18.6 to 26.4,
    # median 22.6; a printed ink, never the black of a screen
    "sumi": (22, 0, 1), "nezumi": (58, 0, 3),
    "ai": (40, 2, -26), "bero": (32, 8, -38),
    "beni": (50, 56, 14), "tan": (58, 42, 52), "shu": (52, 52, 38),
    "ki": (80, 2, 62), "kusa": (55, -22, 30), "murasaki": (38, 24, -20),
    "taisha": (42, 20, 30), "cha": (34, 10, 18),
    "odo": (66, 10, 38),                       # 黄土, yellow ochre: earth, roads, thatch, wood in the light
}


def _lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def _hue_d(a, b):
    ha, hb = np.arctan2(a[2], a[1]), np.arctan2(b[2], b[1])
    return abs((ha - hb + np.pi) % (2 * np.pi) - np.pi)


def pigment_for(c, pigments, paper_lab, grey_c=8.0):
    """The pigment and the strength (0..1) that print nearest to a colour on the paper: grey colours take sumi or its
    grey, coloured ones the pigment nearest in hue among those that can reach their lightness."""
    L, a, b = (float(v) for v in c)
    C = np.hypot(a, b)
    best = None
    for name, p in pigments.items():
        p = np.array(p, np.float32)
        Cp = np.hypot(p[1], p[2])
        if C < grey_c and Cp > 10:
            continue                                # a grey is printed in ink, not in a colour
        if C >= grey_c and Cp < 10:
            continue
        # strength from lightness: the paper's lightness at 0, the pigment's at 1
        k = float(np.clip((paper_lab[0] - L) / max(1.0, paper_lab[0] - p[0]), 0.05, 1.0))
        printed = paper_lab + (p - paper_lab) * k
        d = np.linalg.norm(printed - np.array([L, a, b])) + (25.0 * _hue_d(p, c) if C >= grey_c else 0.0)
        if best is None or d < best[0]:
            best = (d, name, k)
    return best[1], best[2]


def run(subject, style, cel, alpha, parts, U, seed=7):
    ws = style.get("woodblock", {})
    h, w = alpha.shape
    within = alpha > 0.5
    rng = np.random.default_rng(seed)
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    kinds_arr = np.array([""] + kinds[1:])
    paper_kind = ws.get("paper", "washi")
    paper_rgb = tx.sheet_rgb(paper_kind)
    paper_lab = np.array(tx.SHEETS[paper_kind], np.float32)
    pigments = {**PIGMENTS, **{k: tuple(v) for k, v in ws.get("pigments", {}).items()}}
    pl = _lin(paper_rgb)
    printed = np.ones((h, w, 3), np.float32) * pl
    report = []
    grain_amt = ws.get("grain", 0.07)
    # the woodgrain: long wavy bands across each block, a little different per block
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    warp = tx.fbm(rng, h, w, U.len(160.0), octaves=3) * U.len(9.0)
    # each block's colour read off the fill, not the outline (a thin part, an earring, is mostly its outline)
    fill_lines = _lines.find_lines(cel, subject.get("upscaled", 1)) > 0.3
    for lay in _flat.layers(cel, parts, within, kinds, lines=fill_lines):
        j, m = lay["part"], lay["mask"]
        kind = lay["kind"]
        if kind == "eyes":
            continue
        scene = bool(subject.get("scene"))
        bl = lay["base_lab"]
        hue = float(np.degrees(np.arctan2(bl[2], bl[1])) % 360)
        # in a scene, a cool bluish grey (night stone, a moonlit floor) prints in the greys, not in indigo; warm low
        # browns (wood, earth) keep their earth pigments
        grey_c = ws.get("grey_chroma", 12.0) if (scene and 200 <= hue <= 320) else 8.0
        name, k = pigment_for(bl, pigments, paper_lab, grey_c)
        if scene and name == "sumi" and lay["area"] > 0.04 * within.sum():
            # a large dark block prints as a deep grey, not a solid black mass: the prints keep solid sumi for small
            # things and lines
            k = min(k, ws.get("scene_sumi_cap", 0.8))
        # black hair and black cloth print in solid sumi; in a scene a dark area is mostly shade, not a black thing,
        # so only the near-black takes sumi there
        sumi_below = ws.get("sumi_below", 12.0 if subject.get("scene") else 30.0)
        if lay["base_lab"][0] < sumi_below and kind != "skin":
            name, k = "sumi", 1.0                   # black hair and black cloth: solid sumi, as the prints have it
        if kind == "skin":
            # the prints leave a light skin near the paper, a breath of beni; a darker skin keeps its own value and
            # hue in the earth pigments (a skin printed paper-white whatever its colour would change who the figure is)
            conv = ws.get("skin", 0.06)
            name_s, k_s = pigment_for(bl, pigments, paper_lab, 8.0)
            t = float(np.clip((ws.get("pale_above", 74.0) - bl[0]) / 14.0, 0, 1))
            name, k = ("beni", conv) if t <= 0 else (name_s, max(conv, k_s * t + conv * (1 - t)))
        T = np.clip(_lin(rgb(np.array(pigments[name], np.float32).reshape(1, 1, 3))[0, 0]) / np.maximum(pl, 1e-3),
                    0, 1)
        # bokashi: the part's shadow as a gradation wiped on, strongest in the shadow's middle and fading out
        sh = lay["shadow"].astype(np.float32)
        grad = cv2.GaussianBlur(sh, (0, 0), U.len(6.0)) * m
        bok = np.clip(grad * 1.6, 0, 1) * ws.get("bokashi", 0.55) * (0.3 if kind == "skin" else 1.0)
        dens = np.clip(k + (1 - k) * bok, 0, 1) * m
        # the block's surface: woodgrain and the baren's mottle
        ang = rng.uniform(-0.3, 0.3)
        # growth rings: bands whose spacing itself drifts, sharpened toward the late wood
        period = U.len(rng.uniform(3.0, 5.0)) * (1 + 0.1 * tx.fbm(rng, h, w, U.len(300.0), octaves=2))
        bands = np.sin((yy * np.cos(ang) + xx * np.sin(ang) + warp) / period * 2 * np.pi)
        bands = np.sign(bands) * np.abs(bands) ** 3
        mottle = tx.fbm(rng, h, w, U.len(18.0), octaves=3)
        # the grain shows most in a block printed light; a solid block shows it as a faint sheen. Near full strength a
        # few points of density are many points of lightness (a print darkens fast as it nears solid), so the grain
        # and the mottle fade there; the sheen is laid on the printed lightness instead, a few points either way
        g = grain_amt * (1.0 - 0.7 * dens)
        fade = np.clip(1.0 - dens, 0, 1) ** 0.7
        dens = np.clip(dens * (1 + (g * bands + 0.05 * mottle) * fade), 0, 1)
        # registration: the block lands a hair off the key block. The block is cut a hair wider than its area (as a
        # printer's blocks overlap under the key block's lines), so a block off register overlaps its neighbour
        # instead of leaving a line of bare paper between two colours
        off = U.len(ws.get("offset", 0.5))
        dx, dy = rng.uniform(-1, 1, 2) * off
        r_ov = int(np.ceil(off))
        if r_ov > 0:
            k_ov = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_ov + 1, 2 * r_ov + 1))
            dens = np.where(m, dens, cv2.dilate(dens.astype(np.float32), k_ov) * within)
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        dens = cv2.warpAffine(dens.astype(np.float32), M, (w, h), flags=cv2.INTER_LINEAR)
        fac = 1 - dens[..., None] * (1 - T[None, None, :])
        printed = printed * fac ** (1 + 0.06 * mottle[..., None] * dens[..., None])
        report.append({"part": plist[j - 1]["name"], "pigment": name, "strength": round(k, 2)})
    # the eyes: their darks in sumi, their colour in the nearest pigment, the rest paper
    Lc = lab(cel)
    for p in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        sub = Lc[y0:y1, x0:x1]
        # the features' darks: darker than the face's own skin by a margin (a fixed level takes a dark skin for ink),
        # and only on the face (hair and cloth in the box have their own blocks; a second sumi there prints a box)
        pk = kinds_arr[parts[y0:y1, x0:x1]]
        sk = pk == "skin"
        ref = float(np.median(sub[..., 0][sk])) if sk.sum() > 20 else 60.0
        dark = ((sub[..., 0] < min(35.0, ref - 15.0)) & np.isin(pk, ("skin", "eyes", "accessory"))).astype(np.float32)
        T_s = np.clip(_lin(rgb(np.array(pigments["sumi"], np.float32).reshape(1, 1, 3))[0, 0]) / pl, 0, 1)
        printed[y0:y1, x0:x1] *= 1 - dark[..., None] * (1 - T_s[None, None, :])
    # the key block: the lines carved crisp, in sumi
    # only the lines a carver would cut: the long, clear ones (no specks of fold or shadow edge)
    L_line = _lines.find_lines(cel, subject.get("upscaled", 1))
    if subject.get("scene"):
        # a landscape's key block bounds every area of colour (a painted background draws few lines of its own),
        # except the sky and the far hills, which the prints leave to their gradations
        from _core import boundary
        open_ids = [j for j, p in enumerate(plist, start=1) if p.get("kind") in ("sky", "far")]
        b = boundary(parts).astype(np.float32)
        if open_ids:
            b[cv2.dilate(np.isin(parts, open_ids).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0] = 0
        b = cv2.GaussianBlur(b, (0, 0), max(0.6, U.len(0.3)))
        L_line = np.maximum(L_line, np.clip(b * 2.0, 0, 1))
    face = np.zeros((h, w), bool)
    for p in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        face[max(0, y0):y1, max(0, x0):x1] = True
    L_line = _lines.keep_lines(np.clip((L_line - 0.25) / 0.75, 0, 1),
                               U.area(ws.get("min_line", 60.0 if subject.get("scene") else 18.0)),
                               U.k(3, odd=True), always=face)
    a = cv2.GaussianBlur(np.clip(L_line * 1.3, 0, 1), (0, 0), max(0.6, U.len(0.25)))
    wd = U.len(ws.get("line_width", 0.25))
    if wd > 0.5:
        r = int(np.ceil(wd))
        a = cv2.dilate(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    a = np.clip((a - 0.45) * 6 + 0.5, 0, 1)                         # a carved edge: crisp, a pixel of softness
    ol = _lines.closed_outline(alpha, U.len(ws.get("outline", 1.0)), 3)
    a = np.maximum(a, np.clip((ol - 0.45) * 6 + 0.5, 0, 1)) * within
    a = a * (0.92 + 0.08 * tx.fbm(rng, h, w, U.len(10.0), octaves=2))      # the sumi printed a little unevenly
    T_s = np.clip(_lin(rgb(np.array(pigments["sumi"], np.float32).reshape(1, 1, 3))[0, 0]) / pl, 0, 1)
    printed = printed * (1 - a[..., None] * (1 - T_s[None, None, :]))
    out = _srgb(printed).astype(np.float32)
    # blocks printed over each other saturate at the sumi's own darkness (the key block over a sumi block is the same
    # ink twice, not a darker one): what would go below the sumi is compressed just under it
    f = lab(out)
    floor = float(pigments["sumi"][0]) - ws.get("sumi_floor", 2.0)
    deep = f[..., 0] < floor
    f[..., 0] = np.where(deep, floor - (floor - f[..., 0]) * 0.15, f[..., 0])
    out = np.where(deep[..., None], rgb(f), out).astype(np.float32)
    hgt, _ = tx.paper(paper_kind, h, w, U, seed=seed)
    out = np.clip(out * tx.lit(hgt, U, 0.06)[..., None], 0, 1)
    return out, {"blocks": report, "paper": paper_kind}
