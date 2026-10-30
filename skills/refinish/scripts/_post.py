"""Layers laid over a finished figure, after its engine: the hour's light, a sheet of paper under the paint, film
grain, the halation round bright things on film. A style lists them in `post`, in order:

  {"op": "relight", "hour": "night" | "sunset" | "dusk", ...}   the colours relit for another hour (_relight.py)
  {"op": "paper", "kind": "cold-press" | ... , "strength": 0.6, "tooth": 0.08}
        the sheet's colour shows through the light paint (multiplied in by `strength`, the more where the paint is
        lighter) and its tooth catches the light (`tooth`)
  {"op": "grain", "amount": 0.02, "size": 0.35}                  film grain (u)
  {"op": "halation", "threshold": 0.85, "radius": 6.0, "amount": 0.25, "tint": [1.0, 0.55, 0.4]}
        the red-orange glow film gives round its brightest areas (u)
  {"op": "soften", "radius": 0.35, "amount": 1.0}                 a lens's slight softness (u)
  {"op": "curve", "lift": 0.03, "gain": 0.97, "gamma": [1.0, 1.0, 0.95]}
        a tone curve per channel: lifted blacks, a film stock's colour
  {"op": "focus", "at": "face", "sharp": 60.0, "depth": 260.0, "radius": 5.0, "hot": 2.5}
        a lens's depth of field inside the figure: sharp within `sharp` u of the focus (the face, or [x, y] as
        fractions of the figure's box), softening over the next `depth` u to a blur `radius` u wide, in the lens's
        disc and in linear light, so a bright detail out of focus opens into a disc (bokeh) instead of a smear
  {"op": "bokashi" | "mist" | "wet_sky", ...}
        what a technique does to a landscape, on a scene's subject (scripts/scene_subject.py): a woodblock sky's
        gradation, an ink painting's mist and distance, a watercolour's wet sky (_scene.py)
"""
import cv2
import numpy as np

import _relight
import _texture as tx
from _core import lab


def _lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def apply(layers, out, alpha, parts, subject, U, seed=7):
    """The finished figure with each layer laid over it in turn; returns the new RGB."""
    within = alpha > 0.5
    for layer in layers or []:
        op = layer.get("op")
        if op == "relight":
            feats = np.zeros(alpha.shape, np.float32)
            for p in subject.get("protect", []):
                x0, y0, x1, y1 = (int(v) for v in p["box"])
                feats[max(0, y0):y1, max(0, x0):x1] = 1.0
            kw = {k: v for k, v in layer.items() if k not in ("op", "hour")}
            out = _relight.relight(out, alpha, parts, layer.get("hour", "night"), features=feats, U=U, **kw)
        elif op == "paper":
            kind = layer.get("kind", "cold-press")
            hgt, col = tx.paper(kind, *alpha.shape, U, seed=layer.get("seed", seed))
            sheet = tx.sheet_rgb(kind)
            # the sheet shows through where the paint is light: a multiply weighted by the paint's lightness
            Lp = lab(out)[..., 0:1] / 100.0
            k = layer.get("strength", 0.6) * Lp
            out = out * (1 - k) + out * sheet[None, None, :] * k
            out = out * tx.lit(hgt, U, layer.get("tooth", 0.08))[..., None]
        elif op == "grain":
            out = tx.film_grain(out, within, U, layer.get("amount", 0.02), layer.get("size", 0.35),
                                seed=layer.get("seed", seed), shared=layer.get("shared", 0.9))
        elif op == "halation":
            lin = _lin(out)
            lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            bright = np.clip((lum - layer.get("threshold", 0.85)) / 0.15, 0, 1) * within
            glow = cv2.GaussianBlur(bright, (0, 0), max(1.0, U.len(layer.get("radius", 6.0))))
            tint = np.array(layer.get("tint", [1.0, 0.55, 0.4]), np.float32)
            lin = lin + glow[..., None] * tint[None, None, :] * layer.get("amount", 0.25)
            out = _srgb(lin)
        elif op == "soften":
            # a lens's softness: a slight blur, its strength `amount`, so a photographed cel's edges are not digital
            r = max(0.5, U.len(layer.get("radius", 0.35)))
            out = out + (cv2.GaussianBlur(out, (0, 0), r) - out) * layer.get("amount", 1.0)
        elif op == "curve":
            # a tone curve per channel, as a film stock or a telecine gives it: blacks lifted to `lift`, whites to
            # `gain`, the middle bent by `gamma` (each a number or [r, g, b])
            lift = np.array(layer.get("lift", 0.0), np.float32) * np.ones(3, np.float32)
            gain = np.array(layer.get("gain", 1.0), np.float32) * np.ones(3, np.float32)
            gamma = np.array(layer.get("gamma", 1.0), np.float32) * np.ones(3, np.float32)
            out = lift + (gain - lift) * np.power(np.clip(out, 0, 1), 1.0 / gamma)
        elif op == "focus":
            out = _focus(out, alpha, subject, U, layer)
        elif op in ("bokashi", "mist", "wet_sky"):
            import _scene
            out = _scene.OPS[op](out, parts, subject, U, layer)
        else:
            raise ValueError(f"post op must be relight, paper, grain, halation, soften, curve, focus, bokashi, mist "
                             f"or wet_sky, not {op!r}")
        out = np.where(within[..., None], np.clip(out, 0, 1), out).astype(np.float32)
    return out


def _disc(r):
    n = int(np.ceil(r)) + 1
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    k = np.clip(r + 0.5 - np.hypot(xx, yy), 0, 1)
    return k / k.sum()


def _focus(out, alpha, subject, U, layer):
    """Depth of field inside the figure: each pixel blurred by a disc whose size grows with its distance from the
    focus, made as a few blur levels blended per pixel; premultiplied by the figure's alpha so the background never
    bleeds in; the brightest lights pushed above white before the blur so they open into discs."""
    h, w = alpha.shape
    within = alpha > 0.5
    at = layer.get("at", "face")
    ys, xs = np.nonzero(within)
    if isinstance(at, (list, tuple)):
        fx = xs.min() + at[0] * (xs.max() - xs.min())
        fy = ys.min() + at[1] * (ys.max() - ys.min())
    else:
        eyes = [p["box"] for p in subject.get("protect", []) if "eye" in p.get("name", "")]
        if eyes:
            fx = np.mean([(b[0] + b[2]) / 2 for b in eyes])
            fy = np.mean([(b[1] + b[3]) / 2 for b in eyes])
        elif subject.get("focal"):
            fx, fy = subject["focal"][0]["centre"]
        else:
            fx, fy = xs.mean(), ys.min() + 0.08 * (ys.max() - ys.min())
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.hypot(xx - fx, yy - fy)
    rmax = U.len(layer.get("radius", 5.0))
    rmap = rmax * np.clip((dist - U.len(layer.get("sharp", 60.0))) / max(1.0, U.len(layer.get("depth", 260.0))), 0, 1)
    if rmax < 0.75:
        return out
    a = within.astype(np.float32)
    lin = _lin(out)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hot = layer.get("hot", 2.5)
    boost = 1 + (hot - 1) * np.clip((lum - 0.75) / 0.25, 0, 1)
    pre = lin * boost[..., None] * a[..., None]
    n = int(np.clip(np.ceil(rmax / 2.0) + 1, 2, 6))
    radii = np.linspace(0, rmax, n)
    pos = rmap / max(1e-6, rmax) * (n - 1)
    res = np.zeros_like(lin)
    for k, r in enumerate(radii):
        wk = np.clip(1 - np.abs(pos - k), 0, 1)                # a hat: each level weighted by nearness in blur
        if not (wk > 0).any():
            continue
        if r < 0.5:
            level = lin
        else:
            kern = _disc(r)
            level = cv2.filter2D(pre, -1, kern) / np.maximum(cv2.filter2D(a, -1, kern)[..., None], 1e-4)
        res += wk[..., None] * level
    # the lights pushed above white come back down only where they stayed sharp
    res = np.where((rmap < 0.5)[..., None], lin, res)
    return _srgb(res).astype(np.float32)
