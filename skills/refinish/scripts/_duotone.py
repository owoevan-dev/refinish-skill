"""The duotone engine: a figure in two or three inks (or a gradient of a few colours), with no parts needed.

Under the inks lies a flat finish of the figure, the style's `base`: by default the de-AI engine's strong flatten,
whose areas come from the picture's own lines, so a subject from scripts/auto_parts.py without hints is enough.

Modes, `duotone.mode`:
  gradient  a gradient map (グラデーションマップ): each pixel's lightness looked up in a few colour stops, interpolated
            in Lab. The digital duotone, and the photographic processes that print one colour in many densities:
            sepia toning, the cyanotype's Prussian blue.
  tone      a printer's duotone: one tone value per pixel and each ink laid over it by its own curve (the dark ink
            on the shadows, the light one broad over the middle), the inks filtering each other on the paper.
  separate  the figure's own colours matched by the inks printed over each other, as a two-colour separation does it:
            what is red goes to the red plate, what is dark to the black one, the rest to a mix of both.
  auto      the picture's own two colours: the figure read as one material, painted in its median colour and its
            own shadow by the cel engine, a little of the source left under them.

Screens, `duotone.screen`: `flat` (continuous, a digital duotone), `halftone` (each ink's dots at its own angle: the
darkest ink at 45 degrees, the next at 75, a third at 15, 30 degrees apart against moire), `riso` (a stencil
duplicator: stochastic grain, each drum a little off register, the ink a little uneven).

The ink colours of a preset are the inks' printed look on white paper, approximate: a riso or spot ink's published
swatch is itself an approximation, and the paper changes it.
"""
import cv2
import numpy as np

import _halftone as ht
import _texture as tx
from _core import lab, rgb


def _lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def colour_lab(c):
    """A colour given as Lab [L, a, b] or as "#rrggbb" (sRGB), as Lab."""
    if isinstance(c, str):
        h = c.lstrip("#")
        v = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0
        return lab(v.reshape(1, 1, 3))[0, 0]
    return np.array(c, np.float32)


def paper_rgb(p):
    """The paper: a sheet kind of _texture.py, or a colour."""
    if isinstance(p, str) and not p.startswith("#"):
        return tx.sheet_rgb(p)
    return rgb(colour_lab(p).reshape(1, 1, 3))[0, 0]


def transmit(ink_lab):
    """An ink's transmittance (linear RGB): the colour it prints on white paper, as a filter (on a cream or grey
    sheet it prints darker and warmer, as it does)."""
    col = _lin(rgb(np.asarray(ink_lab, np.float32).reshape(1, 1, 3))[0, 0])
    return np.clip(col, 0.0, 1.0)


def mix(cov, T, paper):
    """The printed colour (sRGB) of coverages cov (..., K) of inks with transmittances T (K x 3) on the paper: each
    ink filters the light by its colour where it lies, paper x prod_i (1 - c_i (1 - T_i))."""
    out = np.ones(cov.shape[:-1] + (3,), np.float32) * _lin(paper)
    for i in range(len(T)):
        out = out * (1 - cov[..., i:i + 1] * (1 - T[i]))
    return _srgb(out).astype(np.float32)


def separate(target_lab, T, paper, steps=None, wL=1.5):
    """The coverage of each ink (N x K) that prints nearest each target colour (N x 3 Lab): every combination of
    coverages on a grid (all the inks over each other), the nearest in Lab with lightness weighted `wL` (a two-colour
    page reads by its values first)."""
    K = len(T)
    steps = steps or {1: 33, 2: 21, 3: 11}.get(K, 7)
    g = np.linspace(0, 1, steps, dtype=np.float32)
    grids = np.meshgrid(*([g] * K), indexing="ij")
    covers = np.stack([q.ravel() for q in grids], axis=1)
    lut = lab(mix(covers.reshape(1, -1, K), T, paper))[0]
    w = np.array([wL, 1.0, 1.0], np.float32)
    out = np.zeros((len(target_lab), K), np.float32)
    for s in range(0, len(target_lab), 2048):
        t = target_lab[s:s + 2048]
        d = (((t[:, None, :] - lut[None, :, :]) * w) ** 2).sum(-1)
        out[s:s + 2048] = covers[d.argmin(1)]
    return out


def _curve(t, pts):
    """A piecewise-linear curve through [[t, value], ...] (t ascending)."""
    p = np.array(pts, np.float32)
    return np.interp(t, p[:, 0], p[:, 1]).astype(np.float32)


def tone_of(L, d):
    """The tone value (0 shadow .. 1 light) of lightness L (0..100) after the style's levels and gamma."""
    lo, hi = d.get("levels", [0.0, 1.0])
    t = np.clip((L / 100.0 - lo) / max(1e-3, hi - lo), 0, 1)
    return np.power(t, d.get("gamma", 1.0)).astype(np.float32)


def gradient(t, stops):
    """t (0..1) through colour stops [[t, colour], ...], interpolated in Lab; returns sRGB."""
    ts = np.array([s[0] for s in stops], np.float32)
    cs = np.array([colour_lab(s[1]) for s in stops], np.float32)
    f = np.stack([np.interp(t, ts, cs[:, i]) for i in range(3)], axis=-1).astype(np.float32)
    return rgb(f)


def _base(subject, style, img, alpha, parts, U, base_name):
    """The flat finish under the inks."""
    from _style import load_style, resolve_style
    bs = load_style(resolve_style(base_name))
    if bs["engine"] == "deai":
        import _deai
        out, _ = _deai.run(subject, bs, img, alpha, parts, U)
    elif bs["engine"] == "cel":
        import _cel
        out, _ = _cel.run(subject, bs, img, alpha, parts, U)
    else:
        raise ValueError(f"a duotone's base must be a deai or cel style, not {bs['engine']!r}")
    return out


def _auto(subject, img, alpha, U, base_name):
    """The picture's own two colours: the whole figure one part of the cel engine (its median colour, its own
    shadow), no features kept apart."""
    import _cel
    from _style import load_style, resolve_style
    one = dict(subject)
    one.update({"parts": [{"name": "all", "kind": "cloth"}], "protect": [], "blush": [], "rules": {}})
    one_map = (alpha > 0.5).astype(np.uint8)
    out, model = _cel.run(one, load_style(resolve_style(base_name)), img, alpha, one_map, U)
    return out, model.get("all", {})


def run(subject, style, img, alpha, parts, U, seed=7):
    d = style.get("duotone", {})
    h, w = alpha.shape
    within = alpha > 0.5
    mode = d.get("mode", "gradient")
    rng = np.random.default_rng(seed)
    info = {"mode": mode}
    if mode == "auto":
        out, model = _auto(subject, img, alpha, U, d.get("base", "tv-cel"))
        info["colours"] = {k: v for k, v in model.items() if k in ("base", "shadow")}
        return out, info
    base = _base(subject, style, img, alpha, parts, U, d.get("base", "deai-strong"))
    Lb = lab(base)
    if mode == "gradient":
        out = gradient(tone_of(Lb[..., 0], d), d["stops"])
        out = np.where(within[..., None], out, base)
    elif mode in ("tone", "separate"):
        paper = paper_rgb(d.get("paper", "#ffffff"))
        inks = [colour_lab(i["colour"]) for i in d["inks"]]
        T = np.array([transmit(c) for c in inks], np.float32)
        K = len(inks)
        cov = np.zeros((h, w, K), np.float32)
        if mode == "tone":
            t = tone_of(Lb[..., 0], d)
            for i, ink in enumerate(d["inks"]):
                cov[..., i] = _curve(t, ink.get("curve", [[0, 1], [1, 0]])) * within
        else:
            q = np.round(Lb[within] / 1.5) * 1.5                 # each colour matched once
            uniq, inv = np.unique(q, axis=0, return_inverse=True)
            cov[within] = separate(uniq.astype(np.float32), T, paper, d.get("steps"), d.get("weight_L", 1.5))[
                np.asarray(inv).ravel()]
        out = _screen(cov, T, paper, d, within, U, rng, seed)
        info["inks"] = [{"lab": [round(float(v), 1) for v in c], "coverage": round(float(cov[..., i][within].mean()), 3)}
                        for i, c in enumerate(inks)]
    else:
        raise ValueError(f"duotone.mode must be gradient, tone, separate or auto, not {mode!r}")
    sheet = d.get("sheet")                                   # the paper's tooth, lit, over everything printed
    if sheet:
        hgt, _ = tx.paper(sheet.get("kind", "hot-press"), h, w, U, seed=seed + 11)
        out = np.clip(out * tx.lit(hgt, U, sheet.get("tooth", 0.05))[..., None], 0, 1)
    return np.where(within[..., None], out, base).astype(np.float32), info


def _screen(cov, T, paper, d, within, U, rng, seed):
    """The coverages printed through the style's screen."""
    h, w, K = cov.shape
    kind = d.get("screen", "flat")
    if kind == "flat":
        return mix(cov, T, paper)
    layers = np.zeros_like(cov)
    if kind == "halftone":
        cell = U.len(d.get("cell", 1.3))
        angles = d.get("angles", [45.0, 75.0, 15.0])
        solid = d.get("solid_above", 0.9)
        # the darkest ink takes the first angle
        order = np.argsort([float(lab(rgb_from_T(t))[0, 0, 0]) for t in T])
        for rank, i in enumerate(order):
            c = cv2.GaussianBlur(cov[..., i], (0, 0), max(0.6, 0.25 * cell)) * within
            Tm = ht.threshold((h, w), cell, angles[rank % len(angles)], d.get("spot", "dot"), seed=seed + i)
            lay = np.where(c >= solid, 1.0, ht.screen(c, Tm, cell))
            lay[c < 0.02] = 0.0
            layers[..., i] = lay
        off = U.len(d.get("offset", 0.3))
    elif kind == "riso":
        # a duplicator's dots are far finer than a pixel at a figure's usual size (a 600 dpi grain is about 0.2 u):
        # the tints read as tints with a fine grain in them, strongest half-way (`grain`), the solids solid with a
        # few starved specks, and the drum's ink a little uneven across the sheet (`uneven`)
        amp = d.get("grain", 0.18)
        solid = d.get("solid_above", 0.85)
        for i in range(K):
            c = cov[..., i]
            n = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0),
                                 max(0.5, U.len(d.get("grain_size", 0.2))))
            n /= n.std() + 1e-6
            lay = np.clip(c + amp * 4 * c * (1 - c) * n, 0, 1)
            lay = np.where(c >= solid, np.where(n > 2.6, 0.45, 1.0), lay)
            dens = 1.0 - d.get("uneven", 0.1) * (tx.fbm(rng, h, w, U.len(50.0), octaves=3) * 0.5 + 0.5)
            layers[..., i] = np.clip(lay * dens, 0, 1) * (c > 0.01)
        off = U.len(d.get("offset", 1.0))
    else:
        raise ValueError(f"duotone.screen must be flat, halftone or riso, not {kind!r}")
    # each plate (each drum) lands a little off the others
    for i in range(K):
        dx, dy = rng.uniform(-1, 1, 2) * off * (0.4 if i == 0 else 1.0)
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        layers[..., i] = cv2.warpAffine(layers[..., i], M, (w, h), flags=cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_CONSTANT)
    return mix(layers, T, paper)


def rgb_from_T(t):
    """An ink's colour (sRGB) from its transmittance on white."""
    return _srgb(np.asarray(t, np.float32)).reshape(1, 1, 3).astype(np.float32)
