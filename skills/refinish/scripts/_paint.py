"""The paint engine: a picture repainted with a brush (gouache, thick paint), the stage-C repaint of a scene made
for a figure.

What the source picture gives: the drawing (shapes, line art), the parts and the local colours. What the style
decides:
  - the masses: each part's light and shadow as one clean shape (the darkest share of its shading at the scale of
    its forms), never merged across;
  - the pieces: the picture's own shapes inside each part and mass, merged generously where detail does not matter
    and sparingly in the face and the hands;
  - values massed per part and mass (how much of their spread is kept), the temperature of light and shadow, a
    palette pulled toward its own main colours (or a scene's);
  - strokes laid dark to light inside each piece, following the part's grain (strands, the knit, the pleats);
  - edges lost here and there in the shade, never on a mass's or a part's own edge;
  - the line art laid back in a darker shade of the colour beside it, crisp in the light and in the face, coming and
    going in the shade; or kept only in the face, the forms modelled by colour alone (thick paint);
  - opaque touches of light where light catches hair and gloss (thick paint).
The eyes and the mouth are kept as drawn."""
import math

import cv2
import numpy as np

import _lines as ln_
from _core import (bgr8_of, boundary, clean_shape, ellipse_mask, grain, lab, lab8, piece_blur, protect_mask,
                   slow_noise)
from _style import kind_of, rule


class Brush:
    """A flat brush of opaque paint: a stroke along a short path, a little ragged at its edges (the paper's tooth and
    the brush's hairs), breaking into streaks toward its end where the paint runs out."""

    def __init__(self, seed):
        self.r = np.random.default_rng(seed)
        n = 512
        g = self.r.random((n // 8, n // 8)).astype(np.float32)
        self.noise = cv2.resize(g, (n, n), interpolation=cv2.INTER_CUBIC)
        self.noise = (self.noise - self.noise.min()) / (np.ptp(self.noise) + 1e-6)

    def mask(self, pts, width, dryness):
        """Alpha of a stroke along pts (N x 2), as a float window and its offset."""
        pts = np.asarray(pts, np.float32)
        pad = width + 4
        x0, y0 = np.floor(pts.min(0) - pad).astype(int)
        x1, y1 = np.ceil(pts.max(0) + pad).astype(int)
        W, H = x1 - x0, y1 - y0
        ss = 3
        big = np.zeros((H * ss, W * ss), np.uint8)
        q = (pts - np.array([x0, y0], np.float32)) * ss
        cv2.polylines(big, [np.int32(np.round(q * 4))], False, 255, max(1, int(round(width * ss))), cv2.LINE_AA, shift=2)
        a = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        d = pts[-1] - pts[0]
        L = float(np.hypot(*d)) or 1.0
        u_dir = d / L
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        rel_x, rel_y = xx - pts[0][0], yy - pts[0][1]
        u = np.clip((rel_x * u_dir[0] + rel_y * u_dir[1]) / L, 0, 1)
        v = rel_x * -u_dir[1] + rel_y * u_dir[0]
        ox, oy = self.r.integers(0, 400, 2)
        streak = self.noise[(np.abs(v * 3.1).astype(int) + oy) % 512, ox % 512]
        edge = self.noise[(yy.astype(int) * 3 + oy) % 512, (xx.astype(int) * 3 + ox) % 512]
        # ragged edge: the soft rim of the stroke is cut by the paper's tooth
        a = np.clip((a - 0.5) * 2.2 + 0.5 + (edge - 0.5) * 0.55 * (1 - np.abs(a - 0.5) * 2), 0, 1)
        dry = np.clip((u - (1 - dryness)) / max(dryness, 1e-3), 0, 1)
        a *= 1 - dry * (streak < 0.55)
        return a, x0, y0


def stroke_path(field, p, length, curve=0.6, step=None):
    """A short path from p along the direction field, both ways from the middle, gently curving with it."""
    h, w = field.shape
    step = step or max(2.0, length / 6.0)

    def walk(sign):
        out, q, prev = [], np.array(p, np.float64), None
        for _ in range(int(length / 2 / step)):
            a = field[int(min(h - 1, max(0, q[1]))), int(min(w - 1, max(0, q[0])))]
            d = np.array([math.cos(a), math.sin(a)])
            if prev is None:
                d = d * sign
            elif np.dot(d, prev) < 0:
                d = -d
            if prev is not None:
                d = curve * d + (1 - curve) * prev
                d /= np.linalg.norm(d) + 1e-9
            q = q + d * step
            out.append(q.copy())
            prev = d
        return out

    back = walk(-1)
    return np.array(back[::-1] + [np.array(p, np.float64)] + walk(1), np.float32)


def run(subject, style, img, alpha, parts_u8, U, seed=None, palette_from=None):
    parts = parts_u8.astype(np.int64)
    plist = subject["parts"]
    R = len(plist) + 1
    h, w = parts.shape
    within = alpha > 0.5
    seed = style.get("seed", 7) if seed is None else seed
    rng = np.random.default_rng(seed)
    s = U.s
    src = cv2.cvtColor((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)
    orig_bgr = src.copy()
    src[~within] = (150, 150, 150)
    rgb01 = cv2.cvtColor(src, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rules = [{}] + [rule(style, subject, p) for p in plist]
    kinds = [None] + [kind_of(p) for p in plist]
    skin = np.isin(parts, [j for j, k in enumerate(kinds) if k == "skin"])
    prot = protect_mask(subject, h, w, img, skin, parts=parts)
    face = ellipse_mask(h, w, subject.get("focal", []))

    # ---- what the picture gives ---------------------------------------------------------------------------------------
    L = lab8(src)
    Lv = L[..., 0]
    smooth = cv2.bilateralFilter(src, U.k(9, odd=True), 24, 5 * s)
    Ls = lab8(smooth)
    lines = style.get("lines", {})
    L_line = ln_.find_lines(rgb01, subject.get("upscaled", 1))
    is_line = (L_line > 0.3) & within
    L_keep = ln_.keep_lines(L_line, U.area(lines.get("min_area", 8.9)), 3, always=face > 0.5)

    # ---- the masses: each part's light and shadow as one clean shape ------------------------------------------------
    lit = np.zeros((h, w), bool)
    for j in range(1, R):
        m = (parts == j) & within
        core = m & ~is_line
        if core.sum() < 50:
            lit |= m
            continue
        rj = rules[j]
        fs = U.len(rj.get("scale", 2.67))
        num = cv2.GaussianBlur(Lv * core, (0, 0), fs)
        den = cv2.GaussianBlur(core.astype(np.float32), (0, 0), fs)
        Lf = np.where(den > 1e-3, num / np.maximum(den, 1e-3), Lv)
        t = np.percentile(Lf[core], 100 * rj.get("share", 0.30))
        a_sh = clean_shape(core & (Lf < t), m, U.len(rj.get("smooth", 1.33)), U.area(rj.get("min_island", 44.4)),
                           U.area(rj.get("min_hole", 33.3)))
        lit |= m & (a_sh < 0.5)
    litf = lit.astype(np.float32)

    # detail: each part's own, raised in the focal areas (the face, a hand), softened
    det_part = np.array([0.0] + [rules[j].get("detail", 0.25) for j in range(1, R)], np.float32)
    detail = det_part[parts]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for f in subject.get("focal", []):
        (fx, fy), (rx, ry) = f["centre"], f["radii"]
        dist = np.hypot((xx - fx) / rx, (yy - fy) / ry)
        detail = np.maximum(detail, f.get("strength", 1.0) * np.clip(1.25 - dist, 0, 1) ** 1.2)
    detail = np.clip(cv2.GaussianBlur(detail.astype(np.float32), (0, 0), 10 * s), 0, 1) * within
    shade = (1 - litf) * (1 - (detail > 0.55)) * within

    # ---- pieces: superpixels that follow the picture's edges, never across a part or a mass ---------------------------
    seg_src = cv2.bilateralFilter(src, U.k(5, odd=True), 18, 3 * s)
    Lg = lab8(seg_src)
    grad = np.hypot(cv2.Sobel(Lg[..., 0], cv2.CV_32F, 1, 0), cv2.Sobel(Lg[..., 0], cv2.CV_32F, 0, 1))
    grad += np.hypot(cv2.Sobel(Lg[..., 1], cv2.CV_32F, 1, 0), cv2.Sobel(Lg[..., 2], cv2.CV_32F, 0, 1)) * 0.5
    pc_cfg = style.get("pieces", {})
    sp = max(2, int(round(U.len(pc_cfg.get("size", 2.0)))))
    markers = np.zeros((h, w), np.int32)
    k_ = 1
    for y in range(0, h, sp):
        for x in range(0, w, sp):
            cell = grad[y:y + sp, x:x + sp]
            iy, ix = np.unravel_index(int(np.argmin(cell)), cell.shape)
            markers[y + iy, x + ix] = k_
            k_ += 1
    cv2.watershed(seg_src, markers)
    mkf = np.where(markers < 1, 0, markers).astype(np.float32)
    for _ in range(3):
        mkf = np.where(mkf == 0, cv2.dilate(mkf, np.ones((3, 3), np.uint8)), mkf)
    _, markers = np.unique(mkf.astype(np.int64) * (2 * R) + parts * 2 + lit, return_inverse=True)
    markers = markers.reshape(h, w)
    n_lab = int(markers.max()) + 1
    flat = markers.ravel()
    cnt = np.bincount(flat, minlength=n_lab).astype(np.float64)
    part_sp = np.zeros(n_lab, np.int64)
    part_sp[flat] = parts.ravel()
    lit_sp = np.zeros(n_lab, bool)
    lit_sp[flat] = lit.ravel()
    nl = (~is_line).ravel().astype(np.float64)
    cnt_nl = np.bincount(flat, weights=nl, minlength=n_lab)
    means = np.stack([np.bincount(flat, weights=Lg[..., c].ravel() * nl, minlength=n_lab) for c in range(3)], 1)
    means /= np.maximum(cnt_nl, 1)[:, None]
    det_sp = np.bincount(flat, weights=detail.ravel(), minlength=n_lab) / np.maximum(cnt, 1)
    pairs = []
    for A, B, G in ((markers[:, :-1], markers[:, 1:], grad[:, :-1]), (markers[:-1, :], markers[1:, :], grad[:-1, :])):
        m = A != B
        pairs.append(np.stack([np.minimum(A[m], B[m]).astype(np.float64), np.maximum(A[m], B[m]).astype(np.float64),
                               G[m].astype(np.float64)], 1))
    pairs = np.concatenate(pairs, 0)
    key = pairs[:, 0].astype(np.int64) * n_lab + pairs[:, 1].astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    edge_g = np.bincount(inv, weights=pairs[:, 2]) / np.bincount(inv)
    pa, pb = (uk // n_lab).astype(int), (uk % n_lab).astype(int)
    dE = np.linalg.norm(means[pa] - means[pb], axis=1)
    parent = np.arange(n_lab)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    gen = pc_cfg.get("merge", 1.0)
    for i in np.argsort(dE):
        a_, b_ = pa[i], pb[i]
        if part_sp[a_] != part_sp[b_] or lit_sp[a_] != lit_sp[b_] or part_sp[a_] == 0:
            continue
        det = max(det_sp[a_], det_sp[b_])
        if dE[i] > (9.0 - 5.5 * det) * gen or edge_g[i] > (24.0 - 10.0 * det) * gen:
            continue
        ra, rb = find(a_), find(b_)
        if ra != rb:
            parent[rb] = ra
    roots = np.array([find(i) for i in range(n_lab)])
    _, piece = np.unique(roots[markers], return_inverse=True)
    piece = piece.reshape(h, w)
    n_p = int(piece.max()) + 1
    fp = piece.ravel()
    pc = np.bincount(fp, minlength=n_p).astype(np.float64)
    pc_nl = np.bincount(fp, weights=nl, minlength=n_p)
    base = np.stack([np.bincount(fp, weights=L[..., c].ravel() * nl, minlength=n_p) for c in range(3)], 1)
    base /= np.maximum(pc_nl, 1)[:, None]
    lineonly = pc_nl < 1
    if lineonly.any():                                               # a piece of nothing but line: its own colour
        allm = np.stack([np.bincount(fp, weights=L[..., c].ravel(), minlength=n_p) for c in range(3)], 1) / pc[:, None]
        base[lineonly] = allm[lineonly]
    p_part = np.zeros(n_p, np.int64)
    p_part[fp] = parts.ravel()
    p_lit = np.zeros(n_p, bool)
    p_lit[fp] = lit.ravel()
    p_det = np.bincount(fp, weights=detail.ravel(), minlength=n_p) / pc

    # ---- values massed per part and mass; the colour of light and shadow; the palette ----------------------------------
    med = {}
    for j in range(1, R):
        for lt in (False, True):
            m = (parts == j) & (lit == lt) & ~is_line
            if m.sum() > 20:
                med[(j, lt)] = float(np.median(Lv[m]))
    pal = style.get("palette", {})
    pal_src = [Ls[within & ~is_line].reshape(-1, 3)]
    if palette_from:                                                  # the scene the figure stands in
        scene = cv2.imread(str(palette_from))
        if scene is not None:
            pal_src.append(lab8(cv2.resize(scene, (scene.shape[1] // 4, scene.shape[0] // 4))).reshape(-1, 3))
    centres = []
    for smp in pal_src:
        smp = smp[rng.integers(0, len(smp), min(40000, len(smp)))].astype(np.float32)
        _, _, c = cv2.kmeans(smp, int(pal.get("k", 16)), None,
                             (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5), 3, cv2.KMEANS_PP_CENTERS)
        centres.append(c)
    centres = np.concatenate(centres, 0)
    values = style.get("values", {})
    warm = np.array(values.get("light_shift", [0, 0, 0]), np.float32)     # added to the lit pieces (L, a, b)
    cool = np.array(values.get("shadow_shift", [0, 0, 0]), np.float32)   # added to the shaded pieces
    pull = pal.get("pull", 0.2)
    for i in range(n_p):
        j = int(p_part[i])
        if j == 0:
            continue
        rj = rules[j]
        lt = bool(p_lit[i])
        kp = rj.get("keep_lit", 0.8) if lt else rj.get("keep", 0.62)
        kv = min(1.0, kp + 0.3 * p_det[i])
        c = base[i].copy()
        mv = med.get((j, lt), c[0])
        c[0] = mv + (c[0] - mv) * kv
        c = c + (warm if lt else cool) * rj.get("temperature", 1.0)
        d = np.linalg.norm(centres - c, axis=1)
        base[i] = c + (centres[int(np.argmin(d))] - c) * pull
    fill = base[piece].astype(np.float32)
    canvas = fill.copy()

    # ---- stroke directions: each part's own, bent toward the picture's grain --------------------------------------------
    strokes_cfg = style.get("strokes", {})
    gray = cv2.cvtColor(smooth, cv2.COLOR_BGR2GRAY).astype(np.float32)
    along, coh = grain(gray, U.len(strokes_cfg.get("grain", 1.0)))
    default = np.zeros((h, w), np.float32)
    follow = np.zeros((h, w), np.float32)
    for j in range(1, R):
        m = parts == j
        default[m] = np.radians(float(rules[j].get("stroke_direction", 90)))
        follow[m] = rules[j].get("stroke_follow", 0.6)
    t_ = follow * np.clip((coh - 0.2) / 0.3, 0, 1)
    field = (0.5 * np.arctan2(t_ * np.sin(2 * along) + (1 - t_) * np.sin(2 * default),
                              t_ * np.cos(2 * along) + (1 - t_) * np.cos(2 * default))).astype(np.float32)

    # ---- strokes, dark to light, each inside its own piece ------------------------------------------------------------
    brush = Brush(seed)
    vary_p = np.array([1.0] + [rules[j].get("stroke_vary", 1.0) for j in range(1, R)], np.float32)
    sc = strokes_cfg.get("scale", 1.0) * s

    def paint_layer(spacing, length, width, sigma, threshold, gate, dryness, vary, curve=0.6):
        ref = piece_blur(Ls, piece, sigma)
        ref_mean = np.stack([np.bincount(fp, weights=ref[..., c].ravel(), minlength=n_p) for c in range(3)], 1) / pc[:, None]
        diff = np.linalg.norm(ref - canvas, axis=2)
        strokes = []
        for y in range(spacing // 2, h, spacing):
            for x in range(spacing // 2, w, spacing):
                jx = int(min(w - 1, max(0, x + rng.integers(-spacing // 2, spacing // 2 + 1))))
                jy = int(min(h - 1, max(0, y + rng.integers(-spacing // 2, spacing // 2 + 1))))
                pid = piece[jy, jx]
                if p_part[pid] == 0 or gate[jy, jx] < rng.random():
                    continue
                cell = diff[max(0, jy - spacing // 2):jy + spacing // 2 + 1, max(0, jx - spacing // 2):jx + spacing // 2 + 1]
                if cell.mean() < threshold:
                    continue
                kv = vary(detail[jy, jx]) * vary_p[p_part[pid]]
                col = fill[jy, jx] + (ref[jy, jx] - ref_mean[pid]) * np.array([kv, kv * 0.9, kv * 0.9])
                strokes.append((float(col[0]), jx, jy, col, length * rng.uniform(0.7, 1.25),
                                width * rng.uniform(0.8, 1.2), pid))
        strokes.sort(key=lambda s_: s_[0])
        for _, x, y, col, L_len, wd, pid in strokes:
            pts = stroke_path(field, (x, y), L_len, curve)
            am, ox, oy = brush.mask(pts, wd, dryness)
            x0, y0 = max(0, ox), max(0, oy)
            x1, y1 = min(w, ox + am.shape[1]), min(h, oy + am.shape[0])
            if x1 <= x0 or y1 <= y0:
                continue
            inside = (piece[y0:y1, x0:x1] == pid).astype(np.float32)
            sub = (am[y0 - oy:y1 - oy, x0 - ox:x1 - ox] * inside)[..., None]
            canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - sub) + col * sub
        return len(strokes)

    ones = within.astype(np.float32)
    n1 = paint_layer(int(12 * sc), 34 * sc, 10 * sc, 4 * sc, 3.0, ones, 0.35, lambda d: 0.3 + 0.4 * d)
    n2 = paint_layer(max(2, int(6 * sc)), 16 * sc, 5 * sc, 2 * sc, 4.0, np.clip(detail * 1.4 + 0.2, 0, 1) * ones, 0.3,
                     lambda d: 0.4 + 0.45 * d)
    n3 = paint_layer(max(2, int(3 * sc)), 8 * sc, 2.4 * sc, 1.0 * s, 5.0, np.clip((detail - 0.4) * 2.5, 0, 1) * ones,
                     0.2, lambda d: 0.6 + 0.4 * d, 0.75)
    cm = np.stack([np.bincount(fp, weights=canvas[..., c].ravel(), minlength=n_p) for c in range(3)], 1) / pc[:, None]
    fm = np.stack([np.bincount(fp, weights=fill[..., c].ravel(), minlength=n_p) for c in range(3)], 1) / pc[:, None]
    canvas += (fm - cm).astype(np.float32)[piece]                   # dark-to-light strokes brighten: back to the mean

    # the picture's own fine detail in the face
    texture = style.get("texture", {})
    hp = L - cv2.GaussianBlur(L, (0, 0), 1.2)
    canvas = canvas + hp * np.clip((detail - 0.6) * 2.5, 0, 1)[..., None] * texture.get("face_detail", 0.6)

    # ---- edges in the shade: lost between close big pieces, softened here and there; never on the mass's own edge -------
    keep_edge = np.clip(cv2.dilate(boundary(lit.astype(np.uint8)).astype(np.float32)
                                   + boundary(parts.astype(np.int32)).astype(np.float32), np.ones((3, 3), np.uint8))
                        + (L_keep > 0.3) + prot, 0, 1)
    soft = cv2.dilate(boundary(piece).astype(np.float32), np.ones((3, 3), np.uint8)) * slow_noise(rng, h, w, 40 * s) ** 2
    lost = np.clip(cv2.GaussianBlur(soft, (0, 0), 1.0) * style.get("edges", {}).get("soft", 0.8) * shade * (1 - detail)
                   * (1 - keep_edge), 0, 1)
    canvas = canvas * (1 - lost[..., None]) + cv2.GaussianBlur(canvas, (0, 0), 1.6) * lost[..., None]

    # ---- touches of light: opaque, along the form, where light catches hair and gloss (thick paint) -------------------
    tl = style.get("touches", {}).get("light", {})
    if tl:
        for j in range(1, R):
            if kinds[j] not in tl.get("kinds", []):
                continue
            m = (parts == j) & lit & ~is_line
            if m.sum() < 100:
                continue
            t_hi = np.percentile(Lv[m], 100 * (1 - tl.get("share", 0.06)))
            seeds = np.argwhere(m & (Lv > t_hi))
            if len(seeds) == 0:
                continue
            seeds = seeds[rng.permutation(len(seeds))[:int(len(seeds) * tl.get("density", 0.02)) + 1]]
            for (y, x) in seeds:
                col = canvas[y, x] + np.array([tl.get("lift", 10.0), 0, 2.0], np.float32)
                pts = stroke_path(field, (int(x), int(y)), U.len(tl.get("length", 3.33)) * rng.uniform(0.6, 1.3), 0.7)
                am, ox, oy = brush.mask(pts, U.len(tl.get("width", 1.0)) * rng.uniform(0.7, 1.2), 0.5)
                x0, y0 = max(0, ox), max(0, oy)
                x1, y1 = min(w, ox + am.shape[1]), min(h, oy + am.shape[0])
                if x1 <= x0 or y1 <= y0:
                    continue
                inside = (parts[y0:y1, x0:x1] == j).astype(np.float32)
                sub = (am[y0 - oy:y1 - oy, x0 - ox:x1 - ox] * inside)[..., None]
                canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - sub) + col * sub

    # ---- the line art: a darker shade of the colour beside it; crisp in the light and the face, coming and going in
    #      the shade; or only in the face (thick paint) ------------------------------------------------------------------
    out_rgb = cv2.cvtColor(bgr8_of(canvas), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    found = np.clip(detail * 1.5 + litf * 0.5, 0, 1)
    come_go = slow_noise(rng, h, w, 60 * s)
    a = np.clip(L_keep * 1.15 * lines.get("strength", 0.9), 0, 1) ** 0.9
    a = a * (found + (1 - found) * come_go * lines.get("shade_keep", 1.0))
    if lines.get("face_only"):
        a = a * np.clip((detail - 0.5) * 3, 0, 1)
    if lines.get("outer", 0) > 0:
        mm = within.astype(np.uint8)
        near = np.clip(1 - cv2.distanceTransform(mm, cv2.DIST_L2, 5) / (3.0 * s), 0, 1) * mm
        a = np.maximum(a, near * lines["outer"] * (found + (1 - found) * come_go))
    under = ln_.fill_under(out_rgb, L_keep)
    col = ln_.trace_colour(under, dark=lines.get("dark", 0.5), cap=lines.get("cap", 42.0), chroma=lines.get("chroma", 1.3))
    # the old line is lifted only where a new one is laid (with no line, the paint beside it already covers it)
    lift = cv2.GaussianBlur(np.clip(cv2.dilate((L_keep > 0.12).astype(np.float32), np.ones((3, 3), np.uint8)), 0, 1),
                            (0, 0), 0.7)
    lift *= cv2.dilate((a > 0.05).astype(np.float32), np.ones((5, 5), np.uint8))
    out_rgb = out_rgb * (1 - lift[..., None]) + under * lift[..., None]
    out_rgb = out_rgb * (1 - a[..., None]) + col * a[..., None]
    # the face's own features as drawn; a little paper grain
    orig = cv2.cvtColor(orig_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    # a mass of pure black (a black coat's deepest folds, a black boot) stays black: a painter lays it in the darkest
    # paint; repainted as a shade of the colour beside it, a black mass comes out grey or brown
    Lo_ = lab(orig)[..., 0]
    k_m = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * max(1, int(round(1.5 * s))) + 1,) * 2)
    mass = cv2.morphologyEx(((Lo_ < 12) & within).astype(np.uint8), cv2.MORPH_OPEN, k_m).astype(np.float32)
    mk = cv2.GaussianBlur(mass, (0, 0), 1.0)[..., None]
    out_rgb = out_rgb * (1 - mk) + np.minimum(out_rgb, orig + 0.03) * mk
    out_rgb = out_rgb * (1 - prot[..., None]) + orig * prot[..., None]
    g = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 0.7) * texture.get("grain", 0.006)
    out_rgb = np.clip(out_rgb + g[..., None], 0, 1)
    return out_rgb, {"strokes": [n1, n2, n3], "pieces": n_p}
