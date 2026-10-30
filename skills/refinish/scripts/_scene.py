"""Scene effects: what the traditional techniques do to a landscape that they do not do to a figure. They read the
scene's kinds (scripts/scene_subject.py: sky, far, water, foliage, ground, ...) and run as `post` layers:

  {"op": "bokashi", "colour": [32, 8, -38], "depth": 0.85, "reach": 0.45, "horizon": null}
        a woodblock print's sky (一文字ぼかし): the top of the sky printed in a deep pigment (Prussian blue by default)
        wiped to nothing a `reach` of the sky's height down, transparent over the paper and the sky's own colour;
        `horizon` [L, a, b] adds a second gradation rising from the horizon (a sunset's red)
  {"op": "mist", "amount": 0.75, "bands": 0.5, "paper": "xuan"}
        an ink painting's distance (留白 and 遠近): the sky left as paper, the far hills faded toward it, everything
        fading with height in the picture, and soft bands of mist where a far plane meets the one before it; a night
        sky (its median L below `night_below`, 45) is instead washed in a pale ink (`night_top`, `night_horizon`)
        with the moon left as paper and the wash lightening round it (烘雲托月)
  {"op": "wet_sky", "blooms": 0.35, "clouds": 0.8}
        a watercolour sky painted wet in wet: one gradation from the sky's top colour to its horizon colour, lightened
        and varied in soft blooms, the clouds left as paper with soft edges
"""
import cv2
import numpy as np

import _texture as tx
from _core import lab, rgb


def _lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def kind_mask(parts, subject, *kinds):
    ids = [j for j, p in enumerate(subject.get("parts", []), start=1) if p.get("kind") in kinds]
    return np.isin(parts, ids) if ids else np.zeros(parts.shape, bool)


def _rows(mask):
    r = np.nonzero(mask.any(axis=1))[0]
    return (int(r.min()), int(r.max())) if len(r) else (0, mask.shape[0] - 1)


def bokashi(out, parts, subject, U, layer):
    sky = kind_mask(parts, subject, "sky")
    if not sky.any():
        return out
    h, w = sky.shape
    y0, y1 = _rows(sky)
    reach = max(1.0, layer.get("reach", 0.45) * (y1 - y0 + 1))
    yy = np.arange(h, dtype=np.float32)[:, None]
    t = np.clip(1.0 - (yy - y0) / reach, 0, 1) ** 1.6 * layer.get("depth", 0.85)
    # the wipe is not perfectly level: a woodblock printer wipes the block by hand
    rng = np.random.default_rng(layer.get("seed", 3))
    wob = cv2.resize(rng.standard_normal((1, max(2, w // 64))).astype(np.float32), (w, 1),
                     interpolation=cv2.INTER_CUBIC) * 0.04 * reach
    t = np.clip(1.0 - (yy - y0 - wob) / reach, 0, 1) ** 1.6 * layer.get("depth", 0.85)
    ink = _lin(rgb(np.array(layer.get("colour", [32, 8, -38]), np.float32).reshape(1, 1, 3))[0, 0])
    k = (cv2.GaussianBlur(sky.astype(np.float32), (0, 0), max(1.0, U.len(1.5))) * t)[..., None]
    lin = _lin(out)
    lin = lin * (1 - k * (1 - ink))                     # a transparent pigment: it filters what lies under it
    hz = layer.get("horizon")
    if hz:
        reach2 = max(1.0, layer.get("horizon_reach", 0.35) * (y1 - y0 + 1))
        t2 = np.clip(1.0 - (y1 - yy) / reach2, 0, 1) ** 1.6 * layer.get("horizon_depth", 0.6)
        ink2 = _lin(rgb(np.array(hz, np.float32).reshape(1, 1, 3))[0, 0])
        k2 = (cv2.GaussianBlur(sky.astype(np.float32), (0, 0), max(1.0, U.len(1.5))) * t2)[..., None]
        lin = lin * (1 - k2 * (1 - ink2))
    return _srgb(lin).astype(np.float32)


def mist(out, parts, subject, U, layer):
    h, w = parts.shape
    paper = tx.sheet_rgb(layer.get("paper", "xuan"))
    sky = kind_mask(parts, subject, "sky")
    far = kind_mask(parts, subject, "far")
    yy = np.repeat(np.arange(h, dtype=np.float32)[:, None], w, axis=1) / max(1, h - 1)
    # depth: the sky is all paper; the far hills mostly; the rest by height in the picture (higher is farther)
    # an interior (almost no sky) has no distance by height: its ceiling is no farther than its floor
    interior = sky.sum() < layer.get("interior_below", 0.04) * h * w
    depth = (0.0 if interior else 0.55) * np.clip(1.0 - yy, 0, 1) ** 1.8
    depth = np.where(far, np.maximum(depth, 0.72), depth)
    f0 = lab(out)
    night = bool(sky.any()) and float(np.median(f0[sky][:, 0])) < layer.get("night_below", 45.0)
    night_sky = None
    if night:
        # a night sky is not left as paper: it is washed in a pale ink, darker toward the top, and the moon is the
        # paper left in it, the wash lightening round it (烘雲托月, the moon brought out by the clouds round it)
        moon = sky & (f0[..., 0] > 75)
        moon = cv2.morphologyEx(moon.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        y0, y1 = _rows(sky)
        t = np.clip((yy * (h - 1) - y0) / max(1, y1 - y0), 0, 1)
        L_sky = layer.get("night_top", 52.0) + (layer.get("night_horizon", 72.0) - layer.get("night_top", 52.0)) * t
        halo = cv2.GaussianBlur(moon.astype(np.float32), (0, 0), max(2.0, U.len(30.0)))
        halo = halo / max(1e-6, float(halo.max())) if halo.max() > 0 else halo
        pl = lab(paper.reshape(1, 1, 3).astype(np.float32))[0, 0]
        L_sky = L_sky + (pl[0] - L_sky) * 0.6 * halo
        L_sky = np.where(moon, pl[0], L_sky)
        night_sky = rgb(np.dstack([L_sky, np.full_like(L_sky, pl[1]), np.full_like(L_sky, pl[2])]).astype(np.float32))
        depth = np.where(sky, 0.0, depth)                         # (the sky is painted below, not misted)
    else:
        depth = np.where(sky, 1.0, depth)
    depth = cv2.GaussianBlur(depth.astype(np.float32), (0, 0), max(1.0, U.len(6.0)))
    k = np.clip(depth * layer.get("amount", 0.75), 0, 1)
    # bands of mist where a far plane meets the nearer one before it (its lower edge)
    bands = layer.get("bands", 0.5)
    if bands > 0 and far.any():
        below = np.zeros_like(far)
        below[1:] = far[:-1] & ~far[1:]                   # the lower edge of the far hills
        band = cv2.GaussianBlur(cv2.dilate(below.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32),
                                (0, 0), max(2.0, U.len(14.0)))
        band = band / max(1e-6, band.max())
        k = np.clip(k + bands * band, 0, 1)
    k = k[..., None]
    out = (out * (1 - k) + paper[None, None, :] * k).astype(np.float32)
    if night_sky is not None:
        soft = cv2.GaussianBlur(sky.astype(np.float32), (0, 0), max(1.0, U.len(2.0)))[..., None]
        out = (out * (1 - soft) + night_sky * soft).astype(np.float32)
    return (out * (1 - k) + paper[None, None, :] * k).astype(np.float32)


def wet_sky(out, parts, subject, U, layer):
    sky = kind_mask(parts, subject, "sky")
    if sky.sum() < 100:
        return out
    h, w = sky.shape
    f = lab(out)
    y0, y1 = _rows(sky)
    band = max(2, (y1 - y0) // 6)
    top_m = sky.copy(); top_m[y0 + band:] = False
    bot_m = sky.copy(); bot_m[:max(y0, y1 - band)] = False
    c_top = np.median(f[top_m], axis=0) if top_m.sum() > 20 else np.median(f[sky], axis=0)
    c_bot = np.median(f[bot_m], axis=0) if bot_m.sum() > 20 else c_top
    c_bot = c_bot.copy()
    c_bot[0] = min(97.0, max(c_bot[0], c_top[0]) + 6.0)  # paler toward the horizon, as a wash thins
    yy = np.clip((np.arange(h, dtype=np.float32)[:, None] - y0) / max(1, y1 - y0), 0, 1)
    grad = c_top[None, None, :] * (1 - yy[..., None]) + c_bot[None, None, :] * yy[..., None]
    grad = np.broadcast_to(grad, (h, w, 3)).copy()
    # blooms: the wash pooling and backing off in soft, slow shapes
    rng = np.random.default_rng(layer.get("seed", 9))
    n = tx.fbm(rng, h, w, U.len(90.0), octaves=3)
    grad[..., 0] += layer.get("blooms", 0.35) * 10.0 * n
    grad[..., 1:] *= (1.0 + 0.15 * layer.get("blooms", 0.35) * n)[..., None]
    # the clouds: the lightest, quietest parts of the sky left as paper, with soft edges
    C = np.hypot(f[..., 1], f[..., 2])
    cloud = sky & (f[..., 0] > np.percentile(f[sky][:, 0], 70)) & (C < 18)
    cloud = cv2.GaussianBlur(cloud.astype(np.float32), (0, 0), max(1.0, U.len(5.0))) * layer.get("clouds", 0.8)
    paper = lab(np.array(layer.get("paper_rgb", [0.97, 0.96, 0.93]), np.float32).reshape(1, 1, 3))[0, 0]
    grad = grad * (1 - cloud[..., None]) + paper[None, None, :] * cloud[..., None]
    soft = cv2.GaussianBlur(sky.astype(np.float32), (0, 0), max(1.0, U.len(2.0)))[..., None]
    return (out * (1 - soft) + rgb(grad) * soft).astype(np.float32)


OPS = {"bokashi": bokashi, "mist": mist, "wet_sky": wet_sky}
