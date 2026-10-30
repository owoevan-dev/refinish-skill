"""The wash engine: a figure painted in transparent washes on paper, from a cel finish of it (the style's `base`).
Two media, `wash.medium`:

  watercolour  each part laid as a light wash of its colour, its shadow as a second glaze over it, the lights left
               as paper (the painter leaves the white, never paints it); every wash with the marks of water on paper:
                 - the pigment gathers at a wash's edge as it dries (edge darkening),
                 - pigment settles in the paper's hollows (granulation),
                 - the wash's density drifts (turbulent flow) and a few blooms where water ran back,
                 - two wet washes touching bleed a little into each other (wet in wet);
               after Curtis et al. 1997 (Computer-generated watercolor) and Bousseau et al. 2006 (the pigment-density
               colour model C' = C - (C - C^2)(d - 1), applied in each layer);
               the line art in a soft pencil or ink of its own, faint.
  ink          sumi-e: no colour but ink; each part a wash of one of the five tones of ink (焦 濃 重 淡 清) by its
               lightness, the lines in a brush line with dry-brush breaks (飛白), the washes feathering into the
               xuan paper; one accent colour may be kept (a vermilion ribbon) with `accent_kinds`.

Style keys, section `wash`: `medium`, `paper`, `edge` (edge darkening), `granulation`, `flow`, `bloom`, `bleed` (u),
`lines` (0..1, the line art's strength), `line_colour` (Lab), `light_paper` (lights left as paper, 0..1), `glaze`
(the shadow glaze's strength), `accent_kinds` (ink: kinds kept in colour), `tones` (ink: the five ink lightnesses).
"""
import cv2
import numpy as np

import _flat
import _lines
import _texture as tx
from _core import ellipse_mask, lab, rgb

INK_TONES = [18.0, 32.0, 50.0, 70.0, 86.0]           # 焦 濃 重 淡 清, Lab lightness on xuan paper


def _density(c, d):
    """Bousseau et al.'s colour modification: the colour c (0..1) seen through a layer of pigment density d (1 = as
    is, above 1 darker, below 1 lighter)."""
    return np.clip(c - (c - c * c) * (d - 1.0), 0, 1)


def _edge_dark(mask, U, width):
    """How near each pixel of a wash lies to its edge (1 at the edge, falling off over `width` u), for the pigment a
    drying wash gathers there."""
    d = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    return np.exp(-d / max(1.0, U.len(width))) * mask


def _wobble(m, rng, U, amount):
    """A wash's edge a little irregular: the mask pushed in and out by smooth noise, as water does on paper."""
    if amount <= 0:
        return m
    h, w = m.shape
    sd = cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(1.0, U.len(0.8)))
    n = tx.fbm(rng, h, w, U.len(6.0), octaves=3) * amount
    # the water runs out past the drawn edge here and there; it never leaves a hole inside the wash
    return m | ((sd + n) > 0.5)


def run(subject, style, cel, alpha, parts, U, seed=7):
    ws = style.get("wash", {})
    medium = ws.get("medium", "watercolour")
    h, w = alpha.shape
    within = alpha > 0.5
    rng = np.random.default_rng(seed)
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    paper_kind = ws.get("paper", "cold-press" if medium == "watercolour" else "xuan")
    paper = np.ones((h, w, 3), np.float32) * tx.sheet_rgb(paper_kind)
    hgt, _ = tx.paper(paper_kind, h, w, U, seed=seed)
    flow = tx.fbm(rng, h, w, U.len(40.0), octaves=4)
    disp = tx.fbm(rng, h, w, U.len(2.0), octaves=2)
    out = paper.copy()
    lays = _flat.layers(cel, parts, within, kinds)
    accent = set(ws.get("accent_kinds", []))
    report = []
    # the line art, found once: its pixels are no shadow (a white shirt's fold lines are its darkest tone, and glazed as
    # its shadow they would burn the collar near-black); the lines are laid again over the washes at the end
    L_line = _lines.find_lines(cel, subject.get("upscaled", 1))
    on_line = cv2.dilate((L_line > 0.3).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    Lcel = lab(cel)
    # a scene with almost no sky is an interior (scripts/scene_subject.py's kinds)
    sky_ids = [j for j, p in enumerate(plist, start=1) if p.get("kind") == "sky"]
    interior = bool(subject.get("scene")) and float(np.isin(parts, sky_ids).mean() if sky_ids else 0.0) < 0.04
    for lay in lays:
        m = lay["mask"]
        kind = lay["kind"]
        if kind == "eyes":
            continue
        base = lay["base_lab"].copy()
        if medium == "ink" and kind not in accent:
            tones = ws.get("tones", INK_TONES)
            Lt = min(tones, key=lambda t: abs(t - base[0]))
            if interior and lay["area"] > 0.04 * within.sum():
                # an interior's large areas are laid in the lighter inks: an ink painter keeps the dark tones for
                # accents, and a dark room in solid 焦墨 reads as a black mass (outdoors the mist lightens the far
                # planes and the near dark areas give the depth, so they keep their tone)
                Lt = max(Lt, sorted(tones)[len(tones) // 2])
            base = np.array([Lt, 0.5, 2.0], np.float32)              # sumi on xuan: a faintly warm grey
        col = rgb(base.reshape(1, 1, 3))[0, 0]
        # the wash: its colour as a transparent layer over the paper, the lights left as paper
        wet = _wobble(m, rng, U, ws.get("wobble", 0.25))
        if base[0] < 45:
            # a dark wash stays inside its own part: wobbling out over a light neighbour it reads as a smudge (a
            # headphone's dark cup over a white collar), not as a wet edge
            own = (parts == lay["part"]) & within
            wet &= cv2.dilate(own.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        a = wet.astype(np.float32)
        if medium == "watercolour":
            # the lights left as paper where they are lights (a shine, an edge of light), not where they are the
            # lit half of the part (a face's lit side keeps its wash)
            light = lay["light"]
            share = light.sum() / max(1, m.sum())
            keep = ws.get("light_paper", 0.85) * (0.35 if kind == "skin" else 1.0) * (1.0 if share < 0.2 else 0.3)
            # a dark part's lights are a thinner wash, not bare paper (white flecks on a dark chair read as noise,
            # a navy hair's shine as a lighter navy); and a light too small to be a deliberate reserve keeps the wash
            keep *= float(np.clip((base[0] - 15.0) / 45.0, 0.35, 1.0))
            n_l, cc_l, st_l, _ = cv2.connectedComponentsWithStats(light.astype(np.uint8), connectivity=8)
            big = np.zeros(n_l, bool)
            big[1:] = st_l[1:, cv2.CC_STAT_AREA] >= U.area(ws.get("min_reserve", 6.0))
            a[big[cc_l] & light] *= 1.0 - keep
        # the marks of water: density drifting, pigment in the paper's hollows, more at the edge. A dark wash is
        # pigment laid thick, which drifts and settles far less visibly than a thin one: at full strength the drift's
        # broad patches read as camouflage on a black coat, so the drift and the settling fade with the wash's darkness
        fk = float(np.clip((base[0] - 10.0) / 50.0, 0.25, 1.0))
        d = 1.0 + (ws.get("flow", 0.12) * flow + ws.get("dispersion", 0.05) * disp) * fk
        d += ws.get("granulation", 0.18) * (0.5 - hgt) * (1.5 if kind in ("cloth-dark", "hair") else 1.0) * fk
        d += ws.get("edge", 0.35) * _edge_dark(wet, U, ws.get("edge_width", 1.2))
        layer_col = _density(np.broadcast_to(col, (h, w, 3)).copy(), d[..., None])
        # a wash multiplies the paper and what lies under it (transparent pigment)
        trans = np.clip(layer_col / np.maximum(tx.sheet_rgb(paper_kind), 1e-3), 0, 1)
        out = out * (1 - a[..., None] * (1 - trans))
        # the shadow: a second glaze of the shadow's colour, its own wet edge
        if lay["shadow"].any():
            # the shadow without the lines in it, and its colour read there (the median of the real shadow, not the
            # part's darkest tone, which on a light part is often its line art)
            sh_px = lay["shadow"] & ~on_line
            if sh_px.sum() < 30:
                sh_px = lay["shadow"]
            sh = _wobble(sh_px, rng, U, ws.get("wobble", 0.25)) & m
            si = np.median(Lcel[sh_px], axis=0)
            if medium == "ink" and kind not in accent:
                tones = ws.get("tones", INK_TONES)
                darker = [t for t in tones if t < base[0] - 4]
                si = np.array([max(darker) if darker else base[0] - 12, 0.5, 2.0], np.float32)
            scol = rgb(np.array(si, np.float32).reshape(1, 1, 3))[0, 0]
            # the glaze's transmittance: what it adds over the base wash
            g_t = np.clip(scol / np.maximum(col, 1e-3), 0, 1)
            fk2 = float(np.clip((float(si[0]) - 10.0) / 50.0, 0.25, 1.0))
            d2 = 1.0 + 0.1 * flow * fk2 + ws.get("edge", 0.35) * 1.3 * _edge_dark(sh, U, ws.get("edge_width", 1.2))
            g_t = _density(np.broadcast_to(g_t, (h, w, 3)).copy(), d2[..., None])
            k = sh.astype(np.float32)[..., None] * ws.get("glaze", 0.9)
            out = out * (1 - k * (1 - g_t))
        report.append({"part": plist[lay["part"] - 1]["name"], "wash_lab": [round(float(v), 1) for v in base]})
    # wet in wet: neighbouring washes bleed a little into each other along their shared edges
    bleed = U.len(ws.get("bleed", 1.5 if medium == "watercolour" else 2.5))
    if bleed > 0.5:
        edges = np.zeros((h, w), np.float32)
        pp = parts * within
        edges[:, 1:] += (pp[:, 1:] != pp[:, :-1])
        edges[1:, :] += (pp[1:, :] != pp[:-1, :])
        band = cv2.GaussianBlur(np.clip(edges, 0, 1), (0, 0), bleed)
        band = np.clip(band * 3, 0, 1) * (0.5 + 0.5 * (tx.fbm(rng, h, w, U.len(15.0), octaves=2) > 0))
        soft = cv2.GaussianBlur(out, (0, 0), bleed)
        out = out * (1 - band[..., None]) + soft * band[..., None]
    # blooms: a few cauliflower marks where water ran back into a drying wash (watercolour only). A bloom forms in a
    # broad wash, and a painter keeps it off a face: its centre is never on the skin, the face or a protected feature,
    # it lies its own radius inside the wash it ran back in, and its ring stays in that wash
    if medium == "watercolour" and ws.get("bloom", 0.3) > 0:
        n = int(ws.get("bloom", 0.3) * 6)
        pp = parts * within
        avoid = np.isin(pp, [j for j, k in enumerate(kinds) if k in ("skin", "eyes")]) | \
            (ellipse_mask(h, w, subject.get("focal", [])) > 0.3)
        for p in subject.get("protect", []):
            x0, y0, x1, y1 = (int(v) for v in p["box"])
            avoid[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
        cut = np.zeros((h, w), bool)
        cut[:, 1:] |= pp[:, 1:] != pp[:, :-1]
        cut[1:, :] |= pp[1:, :] != pp[:-1, :]
        inner = cv2.distanceTransform((~cut & within).astype(np.uint8), cv2.DIST_L2, 3)
        yy, xx = np.ogrid[0:h, 0:w]
        for _ in range(n):
            r = U.len(rng.uniform(8, 20))
            ys, xs = np.nonzero(within & ~avoid & (inner >= 1.2 * r))
            if not len(ys):
                continue
            i = rng.integers(len(ys))
            cy, cx = ys[i], xs[i]
            rr = np.hypot(yy - cy, xx - cx) / r
            own = (pp == pp[cy, cx]).astype(np.float32)
            ring = np.exp(-((rr - 1.0) / 0.08) ** 2) * (rr < 1.4) * own
            inside = (rr < 1.0) * 0.06 * own
            out = np.clip(out * (1 - 0.12 * ring[..., None]) + inside[..., None] * (paper - out), 0, 1)
    # the eyes: as drawn, so the face keeps its look, softened to sit in the wash
    for p in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        sub = cel[y0:y1, x0:x1]
        if medium == "ink":
            g = lab(sub)[..., 0:1]
            sub = rgb(np.concatenate([g, np.zeros_like(g) + 0.5, np.zeros_like(g) + 2.0], -1))
        # the features' darks only: darker than the face's own skin by a margin (a fixed level takes a whole box of
        # dark skin and prints the box), and on the face (hair and cloth in the box have their washes)
        Ls_ = lab(sub)[..., 0]
        pk = np.array([""] + kinds[1:])[parts[y0:y1, x0:x1]]
        sk = pk == "skin"
        ref = float(np.median(Ls_[sk])) if sk.sum() > 20 else 85.0
        ink_ = ((Ls_ < min(60.0, ref - 12.0)) & np.isin(pk, ("skin", "eyes", "accessory", ""))).astype(np.float32)
        ink_ = cv2.GaussianBlur(ink_, (0, 0), 0.8)[..., None]
        out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - ink_) + np.minimum(out[y0:y1, x0:x1], sub) * ink_
    # the lines: faint pencil or sepia ink (watercolour), a brush line with dry-brush breaks (ink)
    # (the line art found above)
    strength = ws.get("lines", 0.55 if medium == "watercolour" else 0.95)
    a_l = np.clip(L_line * 1.2, 0, 1) * within * strength
    if medium == "ink":
        # the brush runs dry in streaks along the stroke: break the line where a streaky noise is low
        g = cv2.GaussianBlur(cel.mean(-1).astype(np.float32), (0, 0), 1.5)
        gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
        ang = np.arctan2(gy, gx)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        streak = np.sin((xx * np.cos(ang) + yy * np.sin(ang)) / U.len(0.35) + 6 * tx.fbm(rng, h, w, U.len(6), 2))
        dry = (streak > ws.get("dry", 0.55)) & (tx.fbm(rng, h, w, U.len(12.0), 2) > 0.1)
        a_l = a_l * np.where(dry, 0.35, 1.0)
        lc = np.array(ws.get("line_colour", [14.0, 0.5, 1.5]), np.float32)
    else:
        lc = np.array(ws.get("line_colour", [38.0, 8.0, 14.0]), np.float32)        # a sepia pencil
    lcol = rgb(lc.reshape(1, 1, 3))[0, 0]
    out = out * (1 - a_l[..., None]) + np.minimum(out, lcol) * a_l[..., None]
    # washes and lines over each other saturate at the medium's darkest (ink: its 焦 tone; watercolour: the darkest
    # mixtures a wash reaches, about L 20); below that they are compressed, never the black of a screen
    floor = ws.get("floor", (ws.get("tones", INK_TONES)[0] - 2.0) if medium == "ink" else 20.0)
    f_ = lab(out)
    deep = (f_[..., 0] < floor) & within
    if deep.any():
        f_[..., 0] = np.where(deep, floor - (floor - f_[..., 0]) * 0.15, f_[..., 0])
        out = np.where(deep[..., None], rgb(f_), out).astype(np.float32)
    out = np.clip(out * tx.lit(hgt, U, 0.05)[..., None], 0, 1)
    return np.where(within[..., None], out, paper).astype(np.float32), {"medium": medium, "washes": report,
                                                                      "paper": paper_kind}
