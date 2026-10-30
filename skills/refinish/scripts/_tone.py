"""The manga engine: a figure finished in black ink and screentone on white paper, the way a manga page is made
from a cel finish of it (the style's `base`).

  - the lines in solid black, a little heavier than the cel's;
  - each part's tones read from its flat paint (base, shadow, a light): a dark part (black hair, a navy uniform)
    becomes solid black (ベタ) with its light left white; a light part (a light skin, a white shirt) stays paper, its
    shadow a light tone; the parts between take a tone from a short catalogue of standard densities, their shadows the
    next one up; a darker skin takes a plain dot tone lighter than its value;
  - parts of about the same density are told apart by the screen's pattern, not its density alone (dots, lines,
    crossed lines, sand), the largest part keeping the plain dot: richness-preserving screening (Qu, Pang, Wong &
    Heng 2008);
  - the eyes kept as drawn, in ink: their darks solid, their middle tones a fine dot, their catch-lights white;
  - the blush as short parallel hatching, as a manga artist draws it.

Style keys, section `tone`: `cell` (u, the screen's cell), `angle`, `levels` (the catalogue of densities),
`white_below` and `black_above` (a base darker than `black_above` goes solid; lighter than `white_below`, paper),
`shadow_step` (how many catalogue steps a shadow is denser than its base), `skin_shadow` (the density of a light
skin's shadow), `skin_paper_below` (a skin lighter than this density stays paper, 0.35), `skin_tone_scale` (a darker
skin's tone as a share of its density, 0.65), `line_grow` (u), `paper` and `ink` (Lab lightness).
"""
import cv2
import numpy as np

import _halftone as ht
import _lines
from _core import lab

PATTERNS = ("dot", "line", "cross", "sand")


def _tones(Lv, m, k=3, min_share=0.03):
    """A part's flat tones (lightness, dark to light) and each pixel's tone index."""
    v = Lv[m]
    if len(v) < 30:
        return np.array([float(np.median(v)) if len(v) else 50.0]), np.zeros(int(m.sum()), np.int32)
    qs = np.percentile(v, np.linspace(100.0 / (2 * k), 100 - 100.0 / (2 * k), k))
    c = np.array(sorted(set(np.round(qs, 1))), np.float64)
    for _ in range(25):
        idx = np.abs(v[:, None] - c[None]).argmin(1)
        new = np.array([v[idx == i].mean() if (idx == i).any() else c[i] for i in range(len(c))])
        if np.allclose(new, c, atol=0.05):
            break
        c = new
    # tones closer than 6 L, or holding almost nothing, are one tone
    idx = np.abs(v[:, None] - c[None]).argmin(1)
    keep = [i for i in range(len(c)) if (idx == i).mean() >= min_share]
    c = c[keep]
    merged = [c[0]]
    for x in c[1:]:
        if x - merged[-1] < 6:
            merged[-1] = (merged[-1] + x) / 2
        else:
            merged.append(x)
    c = np.array(merged)
    return c, np.abs(v[:, None] - c[None]).argmin(1).astype(np.int32)


def _nearest_level(d, levels):
    return int(np.argmin([abs(d - x) for x in levels]))


def run(subject, style, cel, alpha, parts, U, src=None):
    """The manga finish (RGB, grey) of a cel-finished figure; `src` is the source picture (its eyes are inked from
    it), the cel finish when not given."""
    ts = style.get("tone", {})
    h, w = alpha.shape
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    cell = U.len(ts.get("cell", 2.2))
    angle = ts.get("angle", 45.0)
    levels = ts.get("levels", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    white_below, black_above = ts.get("white_below", 0.2), ts.get("black_above", 0.72)
    step = ts.get("shadow_step", 2)
    paper_L, ink_L = ts.get("paper", 97.0), ts.get("ink", 8.0)
    Lv = lab(cel)[..., 0]
    ink = np.zeros((h, w), np.float32)                           # 0 paper .. 1 ink
    # ---- each part: solid, paper or a tone, and its shadow -----------------------------------------------------------
    T_cache = {}

    def T(kind, ang):
        key = (kind, round(ang, 1))
        if key not in T_cache:
            T_cache[key] = ht.threshold((h, w), cell * (0.8 if kind == "line" else 1.0), ang, kind)
        return T_cache[key]

    plan, used = [], {}
    areas = {j: int(((parts == j) & within).sum()) for j in range(1, len(plist) + 1)}
    for j in sorted(areas, key=lambda q: -areas[q]):
        m = (parts == j) & within
        if areas[j] < 30:
            continue
        c, idx = _tones(Lv, m)
        base_i = int(np.argmax(np.bincount(idx, minlength=len(c))))
        d_base = 1.0 - c[base_i] / 100.0
        if kinds[j] == "eyes":
            plan.append((j, "eyes", None, None, c, idx))
            continue
        skin = kinds[j] == "skin"
        if skin:
            # a light skin stays paper; a darker skin takes a dot tone lighter than its value, as a manga artist tones
            # a brown skin (never solid, and never left paper: a dark skin printed white would change who the figure is)
            mode = "paper" if d_base <= ts.get("skin_paper_below", 0.35) else "tone"
        elif d_base >= black_above:
            mode = "solid"
        elif d_base <= white_below:
            mode = "paper"
        else:
            mode = "tone"
        lvl = None
        if mode == "tone":
            lvl = _nearest_level(d_base * (ts.get("skin_tone_scale", 0.65) if skin else 1.0), levels)
        pat = None
        if mode == "tone" and skin:
            pat = "dot"
        elif mode == "tone":
            # parts of one density told apart by their pattern, the largest keeping the plain dot
            n_same = used.get(lvl, 0)
            used[lvl] = n_same + 1
            pat = PATTERNS[n_same % len(PATTERNS)]
        plan.append((j, mode, lvl, pat, c, idx))
    for j, mode, lvl, pat, c, idx in plan:
        m = (parts == j) & within
        ys, xs = np.nonzero(m)
        t_px = np.zeros((h, w), np.int32)
        t_px[ys, xs] = idx
        base_i = int(np.argmax(np.bincount(idx, minlength=len(c))))
        shadow = m & (t_px < base_i)
        light = m & (t_px > base_i)
        if mode == "eyes":
            continue
        if mode == "solid":
            ink[m] = 1.0
            ink[light] = 0.0                                     # the shine on black hair, left white
        elif mode == "paper":
            dens = ts.get("skin_shadow", 0.2) if kinds[j] == "skin" else levels[min(len(levels) - 1, 1)]
            cov = ht.screen(dens, T("dot", angle), cell)
            ink[shadow] = cov[shadow]
        else:
            ang = angle if pat in ("dot", "sand") else (angle - 15.0 if pat == "line" else angle)
            base_cov = ht.screen(levels[lvl], T(pat, ang), cell)
            ink[m] = base_cov[m]
            s_lvl = min(len(levels) - 1, lvl + step)
            sh_cov = ht.screen(levels[s_lvl], T(pat, ang), cell)
            ink[shadow] = sh_cov[shadow]
            ink[light] = 0.0
    # ---- the eyes, inked from the source: darks solid, middle tones a fine dot, catch-lights white ----------------------
    src = cel if src is None else src
    Ls = lab(src)[..., 0]
    fine = ht.threshold((h, w), max(1.5, 0.6 * cell), angle, "dot")
    for p in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        sub = Ls[y0:y1, x0:x1]
        d = np.clip((90.0 - sub) / 70.0, 0, 1)                   # 90 L paper .. 20 L solid
        cov = ht.screen(d, fine[y0:y1, x0:x1], max(1.5, 0.6 * cell))
        cov[sub < 28] = 1.0
        cov[sub > 88] = 0.0
        skin_like = (parts[y0:y1, x0:x1] > 0) & np.isin(parts[y0:y1, x0:x1],
                                                      [i for i, k in enumerate(kinds) if k == "skin"])
        # on skin only the features' darks are inked from the source: darker than the face's own skin by a margin, so
        # a dark skin keeps the tone the rest of its face has (a fixed level inks the whole box and prints a box)
        ref = float(np.median(sub[skin_like])) if skin_like.sum() > 20 else 85.0
        keep = ~skin_like | (sub < min(70.0, ref - 12.0))
        # hair and cloth in the box keep their own solid or tone (inked from the source they print the box's shape)
        pk = np.array([""] + kinds[1:])[parts[y0:y1, x0:x1]]
        keep &= np.isin(pk, ("skin", "eyes", "accessory", ""))
        ink[y0:y1, x0:x1] = np.where(keep, cov, ink[y0:y1, x0:x1])
    # ---- the blush as hatching ------------------------------------------------------------------------------------------
    if subject.get("blush") and ts.get("blush", True):
        hatch = np.zeros((h, w), np.float32)
        for bx, by, rx, ry in [b + [b[2]] if len(b) == 3 else b for b in subject["blush"]]:
            n = 5
            for i in range(n):
                x = bx - rx * 0.7 + i * (1.4 * rx / (n - 1))
                cv2.line(hatch, (int(x + 0.25 * ry), int(by - 0.45 * ry)), (int(x - 0.25 * ry), int(by + 0.45 * ry)),
                         1.0, max(1, int(round(0.35 * U.px))), cv2.LINE_AA)
        ink = np.maximum(ink, hatch * within)
    # ---- the lines in solid black ----------------------------------------------------------------------------------------
    L_line = _lines.find_lines(cel, subject.get("upscaled", 1))
    a_line = np.clip(L_line * 1.25, 0, 1)
    grow = U.len(ts.get("line_grow", 0.3))
    if grow > 0.3:
        r = int(np.ceil(grow))
        a_line = np.maximum(a_line, cv2.dilate(a_line, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2))
                            * (grow / r))
    ol = _lines.closed_outline(alpha, U.len(ts.get("outline", 1.2)), 3)
    ink = np.maximum(ink, np.maximum(a_line, ol) * within)
    # lines inside solid black (ベタ) drawn in white, as a manga artist does, so two black shapes that overlap stay
    # two shapes; black hair keeps its own white shine instead
    if ts.get("white_lines", True):
        solid = np.zeros((h, w), bool)
        for j, mode, *_ in plan:
            if mode == "solid" and kinds[j] != "hair":
                solid |= (parts == j) & within
        ink *= 1 - _lines.reversed_lines(a_line, solid, U.len(ts.get("white_line_margin", 1.5)),
                                          U.area(ts.get("white_line_min", 20.0)))
    g = (paper_L + (ink_L - paper_L) * ink) / 100.0
    # lightness to grey sRGB: L* 0..100 is close enough to the display's own curve for paper and ink
    grey = np.clip(((g + 0.16) / 1.16) ** 3, 0, 1)
    grey = np.where(grey > 0.0031308, 1.055 * grey ** (1 / 2.4) - 0.055, 12.92 * grey)
    out = np.repeat(grey[..., None], 3, axis=2).astype(np.float32)
    info = {"plan": [{"part": plist[j - 1]["name"], "mode": mode, **({"density": levels[lvl], "pattern": pat}
                                                                     if mode == "tone" else {})}
                     for j, mode, lvl, pat, _, _ in plan]}
    return out, info
