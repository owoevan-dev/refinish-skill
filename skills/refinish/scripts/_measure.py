"""Measurements of a picture's finish: what the input check grades a source by, and what a style is measured by
when it is replicated from a reference.

All are measured, not looked at; each is a plain number with its meaning in the docstring."""
import cv2
import numpy as np

import _lines as ln_
from _core import lab, tone_cuts


def outline_coverage(img, alpha, upscaled=1):
    """The share of the figure's outline with a drawn line just inside it, overall and on the edges facing left and
    right (a rim light or a lit side leaves one side unlined). A line counts where the darkest pixel within a few
    source pixels of the edge is clearly darker than the fill 8 to 16 source pixels further in."""
    up = max(1, upscaled)
    within = alpha > 0.5
    d_in = cv2.distanceTransform(within.astype(np.uint8), cv2.DIST_L2, 5)
    edge = within & (d_in <= 1.5)
    Lv = lab(img)[..., 0]
    band = within & (d_in <= 3.5 * up)
    Lb = np.where(band, Lv, 100.0).astype(np.float32)
    k = int(2 * 3.5 * up) | 1
    darkest = cv2.erode(Lb, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    ring = (within & (d_in >= 8 * up) & (d_in <= 16 * up)).astype(np.float32)
    s = 10 * up
    ref = cv2.GaussianBlur(Lv * ring, (0, 0), s) / np.maximum(cv2.GaussianBlur(ring, (0, 0), s), 1e-3)
    lined = (darkest < ref - 15) | (darkest < ref * 0.6)
    gx = cv2.Sobel(cv2.GaussianBlur(alpha, (0, 0), 2), cv2.CV_32F, 1, 0, ksize=3)
    out = {}
    for name, m in (("all", edge), ("left", edge & (gx > 0.02)), ("right", edge & (gx < -0.02))):
        out[name] = round(float((lined & m).sum() / max(1, m.sum())), 3)
    return out, lined & edge


def flatness(img, parts, names, kinds, line, three=("hair", "gloss")):
    """Per part, how much of its lightness its own two (or three, for hair and gloss) tones explain: 1.0 is flat cel
    paint, lower is soft gradients and texture, which a posterisation breaks into blotches."""
    Lv = lab(img)[..., 0]
    out = {}
    for j, n in enumerate(names, start=1):
        m = (parts == j) & ~line
        if m.sum() < 2000 or kinds[j - 1] in ("eyes", "accessory"):
            continue
        v = Lv[m].astype(np.float64)
        k = 3 if kinds[j - 1] in three else 2
        cuts = tone_cuts(v, k)
        idx = np.searchsorted(cuts, v)
        within_var = sum(((v[idx == i] - v[idx == i].mean()) ** 2).sum() for i in range(k) if (idx == i).any())
        out[n] = round(float(1 - within_var / max(1e-9, ((v - v.mean()) ** 2).sum())), 3)
    return out


# ---------------------------------------------------------------------------------------------------- a style's finish

def style_metrics(img, alpha, upscaled=1, parts=None, kinds=None, head_px=None):
    """The finish of a picture as numbers a style file can be written from (references/replicating-a-style.md):

    line_width       median width of the line art, in style units (a thousandth of the subject's height)
    line_darkness    median lightness (L, 0..100) at the lines' centres
    line_to_fill     median of a line's lightness over the fill's beside it (0.5: lines half as light as their
                     fill, the trace colouring's `dark`)
    line_hue_match   how closely the lines' hue follows the fill beside them (1 = coloured lines, 色トレス;
                     0 = one neutral ink)
    line_density     share of the figure covered by line art
    outline          the share of the outline that is lined (all / left / right)
    tones            per part kind: flatness (see flatness) and the shadow's share of the part
    shadow_shift     per part kind: the shadow tone minus the lit tone (dL, da, db, Lab)
    edge_softness    median width, in units, of the step between a part's shadow and lit tones (0 = a crisp cel
                     edge, larger = soft shading)
    chroma           median and 90th-percentile chroma of the figure
    value_range      5th to 95th percentile of lightness
    texture          the residual detail left after an edge-preserving smoothing (0 = flat paint)
    """
    within = alpha > 0.5
    ys = np.nonzero(within.any(axis=1))[0]
    unit = (ys[-1] - ys[0] + 1) / 1000.0 if len(ys) else img.shape[0] / 1000.0
    if head_px:                                 # a figure cut off by the frame: seven heads tall
        unit = 7.0 * head_px / 1000.0
    L = lab(img)
    Lv = L[..., 0]
    L_line = ln_.find_lines(img, upscaled)
    line = (L_line > 0.3) & within
    out = {"unit_px": round(float(unit), 3)}
    # line width: the line art's area over the length of its centre line (the distance transform's ridge), so a
    # width between two whole pixels is measured as such; the soft edge counts by its strength
    if line.sum() > 100:
        dist = cv2.distanceTransform(line.astype(np.uint8), cv2.DIST_L2, 5)
        ridge = line & (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8)) - 1e-3) & (dist > 0.5)
        area = float(np.clip(L_line, 0, 1)[within & (L_line > 0.05)].sum())
        out["line_width"] = round(area / max(1, int(ridge.sum())) / unit, 3) if ridge.any() else None
        out["line_darkness"] = round(float(np.median(Lv[ridge])), 1) if ridge.any() else None
        fill = ln_.fill_under(img, L_line)
        lf = lab(fill)
        # how dark a line is against the fill beside it (the trace colouring's `dark`): line L / fill L
        sel_f = ridge & (lf[..., 0] > 20)
        if sel_f.sum() > 50:
            out["line_to_fill"] = round(float(np.median(Lv[sel_f] / lf[..., 0][sel_f])), 3)
        cl = np.hypot(L[..., 1], L[..., 2])
        cf = np.hypot(lf[..., 1], lf[..., 2])
        sel = ridge & (cf > 8)
        if sel.sum() > 50:
            hl = np.arctan2(L[..., 2][sel], L[..., 1][sel])
            hf = np.arctan2(lf[..., 2][sel], lf[..., 1][sel])
            agree = np.cos(hl - hf) * np.clip(cl[sel] / 10.0, 0, 1)
            out["line_hue_match"] = round(float(np.clip(np.median(agree), 0, 1)), 3)
        out["line_density"] = round(float(line.sum() / max(1, within.sum())), 4)
    cov, _ = outline_coverage(img, alpha, upscaled)
    out["outline"] = cov
    c = np.hypot(L[..., 1], L[..., 2])[within & ~line]
    out["chroma"] = {"median": round(float(np.median(c)), 1), "p90": round(float(np.percentile(c, 90)), 1)}
    v = Lv[within & ~line]
    out["value_range"] = [round(float(np.percentile(v, 5)), 1), round(float(np.percentile(v, 95)), 1)]
    sm = cv2.bilateralFilter(img.astype(np.float32), 0, 0.08, max(1.0, 2 * unit))
    res = np.abs(lab(sm)[..., 0] - Lv)[within & ~line]
    out["texture"] = round(float(np.mean(res)), 2)
    if parts is not None and kinds is not None:
        out["tones"], out["shadow_shift"], out["edge_softness"] = _tones(img, L, Lv, parts, kinds, line, unit)
        if out["tones"]:
            out["flatness_median"] = round(float(np.median([t["flatness"] for t in out["tones"].values()])), 3)
        if out["edge_softness"]:
            out["edge_softness_median"] = round(float(np.median(list(out["edge_softness"].values()))), 3)
    return out


# The numbers that describe the finish itself, not the scene's light (which moves the shadows' share and colour and
# the value range): what a replication is scored on.
FINISH = ("line_width", "line_to_fill", "line_hue_match", "line_density", "chroma.median", "texture",
          "flatness_median", "edge_softness_median")


def _tones(img, L, Lv, parts, kinds, line, unit):
    """Per kind: flatness, the shadow's share, the shadow-minus-lit colour step, and the width of the step."""
    tones, shift, soft = {}, {}, {}
    by_kind = {}
    for j, k in enumerate(kinds, start=1):
        if k in ("eyes", "accessory"):
            continue
        by_kind.setdefault(k, []).append(j)
    for k, js in by_kind.items():
        m = np.isin(parts, js) & ~line
        if m.sum() < 2000:
            continue
        v = Lv[m].astype(np.float64)
        n = 3 if k in ("hair", "gloss") else 2
        cuts = tone_cuts(v, n)
        idx = np.searchsorted(cuts, v)
        wv = sum(((v[idx == i] - v[idx == i].mean()) ** 2).sum() for i in range(n) if (idx == i).any())
        flat = 1 - wv / max(1e-9, ((v - v.mean()) ** 2).sum())
        dark = m & (Lv < cuts[0])
        lit = m & (Lv >= cuts[0]) & (Lv < (cuts[1] if n == 3 else 101))
        tones[k] = {"flatness": round(float(flat), 3), "shadow_share": round(float(dark.sum() / m.sum()), 3)}
        if dark.sum() > 200 and lit.sum() > 200:
            d = np.median(L[dark], axis=0) - np.median(L[lit], axis=0)
            shift[k] = [round(float(x), 1) for x in d]
        # the width of the step: where lightness is between the two tones' medians, as a share of the boundary
        if dark.sum() > 200 and lit.sum() > 200:
            lo_, hi_ = float(np.median(Lv[dark])), float(np.median(Lv[lit]))
            span = hi_ - lo_
            if span > 4:
                mid = m & (Lv > lo_ + 0.2 * span) & (Lv < hi_ - 0.2 * span)
                b = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
                b &= m
                if b.sum() > 50:
                    soft[k] = round(float(mid.sum() / b.sum() / unit), 3)
    return tones, shift, soft
