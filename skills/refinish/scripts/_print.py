"""The screen-print engine: a figure separated into a few spot inks and printed one screen at a time on paper, from
a cel finish of it (the style's `base`).

  - the inks: the darkest becomes the key (the lines and the deepest shadows); the others are the figure's main
    colours, found by clustering its flat paint, or given outright (`inks`, Lab);
  - the separation: each colour the figure holds is matched by one ink or two printed over each other, each at a
    coverage from 0 to 1, in a subtractive model (an ink filters the light the paper sends back, by its own colour);
    the match nearest in colour wins;
  - each ink is screened at its own angle (a coverage below solid becomes a dot pattern of that coverage), so the
    tints read as dots and the solids as flat ink;
  - the screens land a little off each other (registration), the ink lies a little unevenly (the squeegee's pull,
    a few dry specks), and the paper shows through where no ink fell.

Style keys, section `print`: `inks` (how many, default 4, or a list of Lab colours), `cell` (u, the screen), `angles`,
`offset` (u, how far a screen may land off register), `uneven` (the ink's unevenness), `paper` (a sheet kind of
_texture.py), `solid_above` (a coverage printed solid instead of screened).
"""
import cv2
import numpy as np

import _halftone as ht
import _lines
import _texture as tx
from _core import lab, rgb


def _lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def choose_inks(cel, within, k, seed=3, parts=None):
    """k spot inks for a figure: clusters of its flat paint in Lab (weighted by area), the darkest one made the key.
    With the part map, each colour ink is the colour of the largest part it prints (a medoid, not the cluster's mean):
    a cluster that takes a beige coat and a peach skin averages to a pink neither of them is, and the coat prints
    pink."""
    L_all = lab(cel)
    px = L_all[within]
    if len(px) > 120000:
        px = px[np.random.default_rng(seed).choice(len(px), 120000, replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.3)
    cv2.setRNGSeed(seed)
    _, _, c = cv2.kmeans(px.astype(np.float32), k + 1, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    c = c[np.argsort(c[:, 0])]
    if parts is not None:
        bases, areas = [], []
        for j in np.unique(parts[within]):
            m = (parts == j) & within
            if j == 0 or m.sum() < 200:
                continue
            bases.append(np.median(L_all[m], axis=0))
            areas.append(int(m.sum()))
        if bases:
            bases, areas = np.array(bases, np.float32), np.array(areas)
            near = np.argmin(((bases[:, None, :] - c[None, :, :]) ** 2).sum(-1), axis=1)
            for i in range(1, len(c) - 1):                          # the colour inks (not the key, not the paper)
                mine = np.nonzero(near == i)[0]
                if len(mine):
                    c[i] = bases[mine[np.argmax(areas[mine])]]
    # the lightest cluster is the paper (or a near-white part): no ink prints it
    inks = c[:-1].copy()
    inks[0] = [min(18.0, inks[0][0]), inks[0][1] * 0.5, inks[0][2] * 0.5]      # the key: a near-black of its hue
    # an ink is printed at full strength: push each colour ink to a saturated, mid-dark version of itself
    for i in range(1, len(inks)):
        L, a, b = inks[i]
        C = np.hypot(a, b)
        # (a muted cluster is often two neighbouring colours averaged, a beige coat and a skin: pushed far, it prints
        # as neither, a pink coat; a muted ink stays near its own chroma)
        s = min(1.6 if C >= 25 else 1.2, max(1.0, 45.0 / max(C, 1e-3))) if C > 6 else 1.0
        inks[i] = [min(L, 72.0), a * s, b * s]
    return inks


def _transmit(ink_lab, paper_rgb):
    """An ink's transmittance (linear RGB): the colour it prints on the paper, divided by the paper."""
    col = _lin(rgb(np.array(ink_lab, np.float32).reshape(1, 1, 3))[0, 0])
    return np.clip(col / np.maximum(_lin(paper_rgb), 1e-3), 0.0, 1.0)


def separate(target_lab, T, paper_rgb, steps=21):
    """For each target colour (N x 3 Lab), the coverage of every ink (N x K): the best of one ink alone or two inks
    printed over each other, each at a coverage in 0..1, in the subtractive model
    printed = paper x prod_i (1 - c_i (1 - T_i))."""
    K = len(T)
    pl = _lin(paper_rgb)
    cs = np.linspace(0, 1, steps, dtype=np.float32)
    combos, covers = [], []
    for i in range(K):
        for ci in cs:
            col = pl * (1 - ci * (1 - T[i]))
            combos.append(col)
            v = np.zeros(K, np.float32)
            v[i] = ci
            covers.append(v)
        for j in range(i + 1, K):
            for ci in cs[1:]:
                for cj in cs[1:]:
                    col = pl * (1 - ci * (1 - T[i])) * (1 - cj * (1 - T[j]))
                    combos.append(col)
                    v = np.zeros(K, np.float32)
                    v[i], v[j] = ci, cj
                    covers.append(v)
    combos = np.array(combos, np.float32)
    covers = np.array(covers, np.float32)
    lut = lab(_srgb(combos).reshape(1, -1, 3).astype(np.float32))[0]
    # nearest combination per target colour, in Lab, done in chunks
    out = np.zeros((len(target_lab), K), np.float32)
    for s in range(0, len(target_lab), 4096):
        t = target_lab[s:s + 4096]
        d = ((t[:, None, :] - lut[None, :, :]) ** 2).sum(-1)
        out[s:s + 4096] = covers[d.argmin(1)]
    return out


def run(subject, style, cel, alpha, parts, U, seed=7):
    ps = style.get("print", {})
    h, w = alpha.shape
    within = alpha > 0.5
    rng = np.random.default_rng(seed)
    paper_kind = ps.get("paper", "newsprint")
    paper_rgb = tx.sheet_rgb(paper_kind)
    inks = ps.get("inks", 4)
    inks = np.array(inks, np.float32) if isinstance(inks, list) else choose_inks(cel, within, int(inks), seed, parts)
    T = np.array([_transmit(c, paper_rgb) for c in inks], np.float32)
    # the lines go to the key ink, solid
    L_line = _lines.find_lines(cel, subject.get("upscaled", 1))
    a_line = np.clip(L_line * 1.2, 0, 1) * within
    # separate the figure's colours (quantized, so each colour is matched once)
    L = lab(cel)
    q = np.round(L[within] / 2.0) * 2.0
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    cov_u = separate(uniq.astype(np.float32), T, paper_rgb)
    cov = np.zeros((h, w, len(inks)), np.float32)
    cov[within] = cov_u[np.asarray(inv).ravel()]
    cov[..., 0] = np.maximum(cov[..., 0], a_line)
    # smooth the coverages a little at the cell's scale, so a tint is one clean dot field and not speckle
    cell = U.len(ps.get("cell", 1.6))
    for i in range(len(inks)):
        cov[..., i] = cv2.GaussianBlur(cov[..., i], (0, 0), max(0.6, 0.3 * cell)) * within
        cov[..., i] = np.maximum(cov[..., i], a_line) if i == 0 else cov[..., i]
    angles = ps.get("angles", [45.0, 15.0, 75.0, 0.0, 30.0, 60.0])
    solid_above = ps.get("solid_above", 0.92)
    offset = U.len(ps.get("offset", 0.8))
    uneven = ps.get("uneven", 0.12)
    pl = _lin(paper_rgb)
    printed = np.ones((h, w, 3), np.float32) * pl
    report = []
    for i in range(len(inks)):
        c = cov[..., i]
        Tm = ht.threshold((h, w), cell, angles[i % len(angles)], "round" if i else "dot", seed=seed + i)
        layer = np.where(c >= solid_above, 1.0, ht.screen(c, Tm, cell))
        layer[c < 0.03] = 0.0
        # off register: each screen shifted a little, the key the least
        dx, dy = (rng.uniform(-1, 1, 2) * offset * (0.4 if i == 0 else 1.0))
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        layer = cv2.warpAffine(layer, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        # the ink's unevenness: a slow variation in density and a few dry specks
        dens = 1.0 - uneven * (tx.fbm(rng, h, w, U.len(60.0), octaves=3) * 0.5 + 0.5)
        specks = (tx.fbm(rng, h, w, max(1.0, U.len(0.8)), octaves=1) > 0.75).astype(np.float32) * uneven * 2
        k = np.clip(layer * dens - specks * layer, 0, 1)[..., None]
        printed = printed * (1 - k * (1 - T[i][None, None, :]))
        report.append({"ink_lab": [round(float(v), 1) for v in inks[i]], "coverage": round(float(c[within].mean()), 3)})
    out = _srgb(printed).astype(np.float32)
    hgt, _ = tx.paper(paper_kind, h, w, U, seed=seed)
    out = np.clip(out * tx.lit(hgt, U, 0.05)[..., None], 0, 1)
    return out, {"inks": report, "paper": paper_kind}
