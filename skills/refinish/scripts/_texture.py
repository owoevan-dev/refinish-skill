"""Surfaces under and over the paint, all made by code so the skill ships no texture files.

  paper(kind, h, w, U, seed): a sheet's tooth as a height field in 0..1, and the sheet's colour (Lab):
      cold-press  watercolour paper: round bumps of a few units, unevenly packed;
      hot-press   smooth watercolour paper: only a faint long wave;
      washi       Japanese paper: long kozo fibres over a fine felt (woodblock prints);
      xuan        Chinese paper: short fine fibres, a soft cloudy felt (ink wash);
      newsprint   cheap print paper: fine speckle, yellowed (manga, screen prints);
      canvas      a plain weave of a few units (oil, thick paint).
  lit(height, U, strength): the tooth's light and shade, lit from the upper left like the paint.
  film_grain(rgb, within, U, amount, size, seed): film grain made in density, strongest in the middle tones,
      partly shared by the three dye layers so it reads as grain and not as colour noise.

The paper's units follow the figure (references/style-format.md): a tooth of 4 u is a millimetre-sized bump on a
figure a quarter of a metre tall, whatever the picture's pixel size.
"""
import cv2
import numpy as np

from _core import rgb_px

SHEETS = {                                             # the sheet's colour, Lab
    "cold-press": (96.5, 0.2, 3.0), "hot-press": (97.0, 0.0, 2.5), "washi": (94.0, 0.8, 7.5),
    "xuan": (93.5, 0.5, 6.0), "newsprint": (91.0, 0.5, 8.5), "canvas": (92.0, 0.6, 7.0),
}


def fbm(rng, h, w, scale, octaves=4, gain=0.5):
    """Fractal noise in about -1..1: octaves of smooth value noise, the first varying over `scale` pixels."""
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for i in range(octaves):
        s = max(1.0, scale / (2 ** i))
        gh, gw = int(np.ceil(h / s)) + 3, int(np.ceil(w / s)) + 3
        g = rng.standard_normal((gh, gw)).astype(np.float32)
        up = cv2.resize(g, (int(gw * s), int(gh * s)), interpolation=cv2.INTER_CUBIC)
        oy, ox = rng.integers(0, max(1, up.shape[0] - h)), rng.integers(0, max(1, up.shape[1] - w))
        out += amp * up[oy:oy + h, ox:ox + w]
        total += amp
        amp *= gain
    out /= total
    return out / (out.std() + 1e-6) / 3.0


def _bumps(rng, h, w, size):
    """Round bumps packed like a cold-press sheet's: cones round scattered points, rounded off."""
    n = max(4, int(h * w / (size * size) * 1.15))
    pts = np.zeros((h, w), np.uint8)
    pts[rng.integers(0, h, n), rng.integers(0, w, n)] = 1
    d = cv2.distanceTransform(1 - pts, cv2.DIST_L2, 5)
    cone = np.clip(1 - d / (0.75 * size), 0, 1)
    return cv2.GaussianBlur(cone ** 0.7, (0, 0), 0.22 * size)


def _fibres(rng, h, w, count, length, width, curl):
    """Long thin fibres, each a gently curving stroke of its own length and width, anti-aliased."""
    canvas = np.zeros((h, w), np.float32)
    for _ in range(count):
        n = 12
        x, y = rng.uniform(-0.1 * w, 1.1 * w), rng.uniform(-0.1 * h, 1.1 * h)
        ang = rng.uniform(0, np.pi)
        L = length * rng.uniform(0.4, 1.4)
        pts = []
        for _ in range(n):
            pts.append((x, y))
            ang += rng.normal(0, curl)
            x, y = x + np.cos(ang) * L / n, y + np.sin(ang) * L / n
        wd = max(1, int(round(width * rng.uniform(0.5, 1.5))))
        cv2.polylines(canvas, [np.int32(np.round(np.array(pts) * 4))], False, float(rng.uniform(0.4, 1.0)), wd,
                      cv2.LINE_AA, shift=2)
    return cv2.GaussianBlur(canvas, (0, 0), max(0.5, 0.35 * width))


def _weave(h, w, period, rng):
    """A plain weave: warp and weft threads passing over and under each other, a little irregular."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    jitter = fbm(rng, h, w, period * 6, octaves=2) * period * 0.25
    u, v = (xx + jitter) / period, (yy - jitter) / period
    warp = np.abs(np.sin(np.pi * u)) ** 0.6           # a thread's round profile across it
    weft = np.abs(np.sin(np.pi * v)) ** 0.6
    over = ((np.floor(u) + np.floor(v)) % 2).astype(np.float32)
    along_w = 0.6 + 0.4 * np.abs(np.cos(np.pi * v))   # each thread dips where it passes under the other
    along_f = 0.6 + 0.4 * np.abs(np.cos(np.pi * u))
    return np.where(over > 0.5, warp * along_w, weft * along_f)


def paper(kind, h, w, U, seed=11):
    """A sheet's tooth (height 0..1, mean about 0.5) and its colour (Lab)."""
    rng = np.random.default_rng(seed)
    u = U.px
    if kind == "cold-press":
        hgt = 0.75 * _bumps(rng, h, w, 4.0 * u) + 0.25 * (fbm(rng, h, w, 14 * u) * 0.5 + 0.5)
    elif kind == "hot-press":
        hgt = 0.5 + 0.35 * fbm(rng, h, w, 30 * u, octaves=3) + 0.1 * fbm(rng, h, w, 2 * u, octaves=2)
    elif kind == "washi":
        felt = fbm(rng, h, w, 3 * u, octaves=3) * 0.5 + 0.5
        n = int(h * w / (60 * u) ** 2 * 9)
        fib = _fibres(rng, h, w, n, 70 * u, max(1.0, 0.45 * u), 0.18)
        hgt = 0.45 * felt + 0.55 * np.clip(fib, 0, 1)
    elif kind == "xuan":
        felt = fbm(rng, h, w, 9 * u, octaves=4) * 0.5 + 0.5
        n = int(h * w / (30 * u) ** 2 * 6)
        fib = _fibres(rng, h, w, n, 18 * u, max(1.0, 0.3 * u), 0.35)
        hgt = 0.6 * felt + 0.4 * np.clip(fib, 0, 1)
    elif kind == "newsprint":
        hgt = 0.5 + 0.3 * fbm(rng, h, w, 1.2 * u, octaves=2) + 0.2 * fbm(rng, h, w, 12 * u, octaves=3)
    elif kind == "canvas":
        hgt = 0.8 * _weave(h, w, 3.2 * u, rng) + 0.2 * (fbm(rng, h, w, 20 * u) * 0.5 + 0.5)
    else:
        raise ValueError(f"paper kind must be one of {', '.join(SHEETS)}, not {kind!r}")
    hgt = hgt.astype(np.float32)
    lo, hi = np.percentile(hgt, (1, 99))
    return np.clip((hgt - lo) / max(1e-6, hi - lo), 0, 1).astype(np.float32), np.array(SHEETS[kind], np.float32)


def lit(height, U, strength=1.0, light=(-1.0, -1.0)):
    """The tooth's light and shade as a multiplier about 1, lit from the light's side (upper left by default)."""
    height = np.asarray(height, np.float32)
    gx = cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3)
    lx, ly = np.array(light, np.float32) / np.hypot(*light)
    slope = -(gx * lx + gy * ly) * max(1.0, U.px) / 4.0
    return (1.0 + strength * np.tanh(slope)).astype(np.float32)


def film_grain(img, within, U, amount=0.02, size=0.35, seed=5, shared=0.9):
    """Film grain: noise in optical density, grains `size` u across, strongest in the middle tones (a grain shows
    against grey, hardly in the clear highlights or the full blacks), mostly shared by the three dye layers."""
    rng = np.random.default_rng(seed)
    h, w = within.shape
    sig = max(0.5, size * U.px)

    def layer():
        n = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), sig)
        return n / (n.std() + 1e-6)

    common = layer()
    k = np.sqrt(max(0.0, 1 - shared ** 2))
    T = np.clip(img, 1e-3, 1)
    lum = np.clip(T @ np.array([0.2126, 0.7152, 0.0722], np.float32), 1e-3, 1)
    weight = (4 * lum * (1 - lum)) ** 0.75             # strongest in the middle tones
    out = img.copy()
    for c in range(3):
        n = shared * common + k * layer()
        D = -np.log10(T[..., c]) + amount * weight * n
        out[..., c] = np.where(within, 10 ** (-D), img[..., c])
    return np.clip(out, 0, 1).astype(np.float32)


def sheet_rgb(kind):
    """The sheet's colour as RGB 0..1."""
    return rgb_px(SHEETS[kind])
