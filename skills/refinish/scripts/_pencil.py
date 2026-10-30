"""The pencil engine: a figure as an animator's key drawing (原画), from a cel finish of it (the style's `base`): no
paint, only lines on animation paper.

  - the drawing in graphite: the line art found in the picture, its weight kept, the pencil's grain (the graphite
    catches the paper's tooth, and varies a little along the stroke);
  - the shadows marked as a key animator marks them for the painters (影指定): the boundary of each shadow drawn in a
    coloured pencil, a second colour for the lights and a third for a second shadow; optionally a light hatching
    inside each shadow in its pencil;
  - on smooth animation paper, the figure's ground left as paper.

The colours follow the common convention (a shadow's boundary in blue, a highlight's in red, a second shadow's in
yellow-green); studios differ, so each is the style's to change (`shadow_colour`, `light_colour`, `deep_colour`,
Lab).

Style keys, section `pencil`: `graphite` (Lab), `strength`, `tooth` (how much the paper breaks the graphite),
`colour_width` (u), `hatch` (0..1), `hatch_spacing` (u), `shadow_colour`, `light_colour`, `deep_colour`, `paper`.
"""
import cv2
import numpy as np

import _flat
import _lines
import _texture as tx
from _core import clean_shape, rgb


def _boundary(a, b, width):
    """Pixels of `a` within `width` pixels of `b`: the line where two tones meet, drawn on a's side."""
    r = max(1, int(round(width)))
    near_b = cv2.dilate(b.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    return a & (near_b > 0)


def run(subject, style, cel, alpha, parts, U, seed=7):
    ps = style.get("pencil", {})
    h, w = alpha.shape
    within = alpha > 0.5
    rng = np.random.default_rng(seed)
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    paper_kind = ps.get("paper", "hot-press")
    paper_rgb = tx.sheet_rgb(paper_kind)
    hgt, _ = tx.paper(paper_kind, h, w, U, seed=seed)
    out = np.ones((h, w, 3), np.float32) * paper_rgb
    # ---- the shadow marks in coloured pencil ----------------------------------------------------------------------
    cw = U.len(ps.get("colour_width", 0.5))
    cols = {"shadow": np.array(ps.get("shadow_colour", [42.0, 8.0, -58.0]), np.float32),
            "light": np.array(ps.get("light_colour", [50.0, 66.0, 40.0]), np.float32),
            "deep": np.array(ps.get("deep_colour", [50.0, -50.0, 28.0]), np.float32)}
    marks = {k: np.zeros((h, w), np.float32) for k in cols}
    hatch_amt = ps.get("hatch", 0.0)
    if hatch_amt > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        hatch = (np.abs(((xx + yy) / max(2.0, U.len(ps.get("hatch_spacing", 2.2)))) % 1.0 - 0.5) < 0.12)
    for lay in _flat.layers(cel, parts, within, kinds):
        if lay["kind"] in ("eyes", "accessory"):
            continue
        m = lay["mask"]
        # a clean shadow shape, as the animator would lasso it: no specks, no ragged edge
        sh = clean_shape(lay["shadow"], m, U.len(0.8), U.area(30.0), U.area(20.0)) > 0.5
        base = m & ~sh
        marks["shadow"] = np.maximum(marks["shadow"], _boundary(sh, base, cw).astype(np.float32))
        if hatch_amt > 0:
            marks["shadow"] = np.maximum(marks["shadow"], (sh & hatch).astype(np.float32) * hatch_amt)
        tone = lay["tone"]
        if len(lay["colours"]) >= 3 and lay["base_i"] >= 2:
            deep = clean_shape(m & (tone == 0) & sh, m, U.len(0.8), U.area(20.0), U.area(10.0)) > 0.5
            marks["deep"] = np.maximum(marks["deep"], _boundary(deep, sh & ~deep, cw).astype(np.float32))
        lt = clean_shape(lay["light"], m, U.len(0.6), U.area(12.0), U.area(10.0)) > 0.5
        if lt.any() and lay["kind"] in ("hair", "gloss", "metal"):
            marks["light"] = np.maximum(marks["light"], _boundary(lt, m & ~lt, cw).astype(np.float32))
    grain = 0.75 + 0.25 * np.clip((hgt - 0.25) / 0.5, 0, 1)
    for k, mk in marks.items():
        a = np.clip(cv2.GaussianBlur(mk, (0, 0), 0.6) * 1.3, 0, 1) * grain * ps.get("colour_strength", 1.0) * within
        c = rgb(cols[k].reshape(1, 1, 3))[0, 0]
        out = out * (1 - a[..., None]) + np.minimum(out, c) * a[..., None]
    # ---- the drawing in graphite ------------------------------------------------------------------------------------
    L_line = _lines.find_lines(cel, subject.get("upscaled", 1))
    # the drawing's own lines, not the edges of dark shading (those are marked in colour): long ones, and every
    # line touching the face
    face = np.zeros((h, w), bool)
    for p in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in p["box"])
        face[max(0, y0):y1, max(0, x0):x1] = True
    L_line = _lines.keep_lines(np.clip((L_line - 0.2) / 0.8, 0, 1), U.area(ps.get("min_line", 10.0)),
                               U.k(3, odd=True), always=face)
    a = np.clip(L_line * 1.15, 0, 1) ** 1.1 * ps.get("strength", 0.9)
    tooth = ps.get("tooth", 0.35)
    a = a * (1 - tooth + tooth * np.clip((hgt - 0.2) / 0.5, 0, 1))
    a = a * (0.85 + 0.15 * tx.fbm(rng, h, w, max(1.0, U.len(0.6)), octaves=2))
    ol = _lines.closed_outline(alpha, U.len(ps.get("outline", 0.8)), 3) * 0.9
    # where two parts meet and the picture drew no line (dark hair against the face, black on black), the
    # animator still draws one
    pp = np.where(within, parts, 0)
    edge = np.zeros((h, w), np.float32)
    edge[:, 1:] = np.maximum(edge[:, 1:], (pp[:, 1:] != pp[:, :-1]) & (pp[:, 1:] > 0) & (pp[:, :-1] > 0))
    edge[1:, :] = np.maximum(edge[1:, :], (pp[1:, :] != pp[:-1, :]) & (pp[1:, :] > 0) & (pp[:-1, :] > 0))
    minor = np.isin(pp, [j for j, k in enumerate(kinds) if k in ("eyes", "accessory")])
    edge = cv2.GaussianBlur(edge * ~minor, (0, 0), max(0.6, U.len(0.2)))
    edge = _lines.keep_lines(np.clip(edge * 2.5, 0, 1), U.area(ps.get("min_line", 10.0)), U.k(3, odd=True)) * 0.8
    a = np.clip(np.maximum(np.maximum(a, ol), edge * (1 - tooth + tooth * np.clip((hgt - 0.2) / 0.5, 0, 1))),
                0, 1) * within
    g = rgb(np.array(ps.get("graphite", [34.0, 0.0, -3.0]), np.float32).reshape(1, 1, 3))[0, 0]
    out = out * (1 - a[..., None]) + np.minimum(out, g) * a[..., None]
    out = np.clip(out * tx.lit(hgt, U, 0.03)[..., None], 0, 1)
    return np.where(within[..., None], out, paper_rgb).astype(np.float32), {"paper": paper_kind}
