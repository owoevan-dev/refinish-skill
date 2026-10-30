"""Halftone screens: the dots, lines and crossed lines a printer or a manga artist makes a grey of from one ink.

A screen is a threshold map T (0..1) laid over the picture: ink goes where the tone to print (0 paper .. 1 full ink)
is above it. T is the screen's spot function evaluated in the screen's own grid (cells `cell` pixels wide, turned
by `angle` degrees), then ranked so that exactly a share t of every cell lies below t: a tone of 0.3 inks 30 % of
the paper whatever the spot's shape.

Spot functions:
  dot     Euclidean dot: round dots that touch at 50 % and turn into round holes past it, as an offset screen does;
  round   round dots all the way up (a manga dot tone: the dots merge into black only at the end);
  line    parallel lines whose width carries the tone;
  cross   two line screens crossed at right angles (a cross-hatch tone);
  sand    stochastic grain (a sand or "noise" tone), the same coverage without a grid.

Edges are anti-aliased: coverage ramps over about a pixel round each threshold, so the dots stay round when the
result is enlarged or reduced a little.
"""
import cv2
import numpy as np

SPOTS = ("dot", "round", "line", "cross", "sand")
_LUT = {}


def _spot(kind, x, y):
    """The spot function on cell coordinates x, y in -1..1 (the cell's centre at 0): higher inks first."""
    if kind == "dot":
        ax, ay = np.abs(x), np.abs(y)
        inner = ax + ay <= 1
        return np.where(inner, 1 - (x * x + y * y) / 2, ((1 - ax) ** 2 + (1 - ay) ** 2) / 2)
    if kind == "round":
        return 1 - np.hypot(x, y) / np.sqrt(2)
    if kind == "line":
        return 1 - np.abs(y)
    if kind == "cross":
        return np.maximum(1 - np.abs(x), 1 - np.abs(y))
    raise ValueError(f"spot must be one of {', '.join(SPOTS)}, not {kind!r}")


def _rank_lut(kind, n=512):
    """The spot function's values ranked over one cell: a table from spot value to the share of the cell below it,
    so the threshold map has an even spread (a tone t inks exactly t of each cell)."""
    if kind not in _LUT:
        g = (np.arange(n) + 0.5) / n * 2 - 1
        X, Y = np.meshgrid(g, g)
        v = np.sort(_spot(kind, X, Y).ravel())
        _LUT[kind] = v
    return _LUT[kind]


def threshold(shape, cell, angle=45.0, kind="dot", seed=3, origin=(0.0, 0.0)):
    """The screen's threshold map (float32, 0..1): ink where the tone is above it."""
    h, w = shape
    if kind == "sand":
        rng = np.random.default_rng(seed)
        n = cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (0, 0), max(0.5, 0.1 * cell))
        r = np.argsort(np.argsort(n.ravel()))                       # ranked: an even spread
        return (r.reshape(h, w) / float(h * w)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xx -= origin[0]
    yy -= origin[1]
    a = np.radians(angle)
    u = (xx * np.cos(a) + yy * np.sin(a)) / cell
    v = (-xx * np.sin(a) + yy * np.cos(a)) / cell
    x = (u - np.floor(u)) * 2 - 1
    y = (v - np.floor(v)) * 2 - 1
    s = _spot(kind, x, y)
    ranked = np.searchsorted(_rank_lut(kind), s.ravel()) / float(len(_rank_lut(kind)))
    return (1.0 - ranked.reshape(h, w)).astype(np.float32)        # the highest spot inks first: lowest threshold


def screen(tone, T, cell, soft=1.0):
    """Ink coverage (0..1) of `tone` (0..1, any shape matching T) through the threshold map T, anti-aliased over
    about `soft` pixels."""
    # one pixel spans about 2/cell of the threshold's range across a dot's edge
    aa = max(1e-3, soft * 2.0 / max(1.0, cell))
    return np.clip((np.asarray(tone, np.float32) - T) / aa + 0.5, 0.0, 1.0).astype(np.float32)
