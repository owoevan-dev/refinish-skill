"""Shared fixtures: the scripts folder on the import path, and a small drawn figure made by code (no picture files
ship with the tests)."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "refinish"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cv2  # noqa: E402


def draw_figure(h=900, w=480, skin=((190, 212, 246), (160, 180, 226))):
    """A cut-out figure drawn the way a character picture is: flat fills with a cel shadow on one side, a dark
    outline round each shape, two eyes with a highlight, a mouth. Skin (BGR lit and shade, light by default), hair, a
    jacket, trousers and shoes."""
    img = np.zeros((h, w, 4), np.uint8)
    ink = (40, 32, 36, 255)

    def shape(draw, fill, shade, light_side=-1):
        m = np.zeros((h, w), np.uint8)
        draw(m)
        ys, xs = np.nonzero(m)
        if not len(xs):
            return m
        cx = xs.mean()
        sh = m.astype(bool) & ((xs.mean() * 0 + np.arange(w)[None, :] - cx) * light_side < -(xs.max() - xs.min()) * 0.12)
        img[m.astype(bool)] = (*fill, 255)
        img[sh] = (*shade, 255)
        cnt, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(img, cnt, -1, ink, 2, cv2.LINE_AA)
        return m

    cx = w // 2
    # BGR colours: trousers, shoes, jacket, neck, face, hair
    shape(lambda m: cv2.rectangle(m, (cx - 80, 560), (cx - 8, 820), 255, -1), (92, 64, 52), (70, 46, 38))
    shape(lambda m: cv2.rectangle(m, (cx + 8, 560), (cx + 80, 820), 255, -1), (92, 64, 52), (70, 46, 38))
    shape(lambda m: cv2.ellipse(m, (cx - 50, 840), (52, 26), 0, 0, 360, 255, -1), (40, 44, 60), (28, 30, 42))
    shape(lambda m: cv2.ellipse(m, (cx + 50, 840), (52, 26), 0, 0, 360, 255, -1), (40, 44, 60), (28, 30, 42))
    shape(lambda m: cv2.rectangle(m, (cx - 120, 300), (cx + 120, 590), 255, -1), (60, 120, 200), (44, 88, 160))
    shape(lambda m: cv2.rectangle(m, (cx - 170, 310), (cx - 120, 560), 255, -1), (60, 120, 200), (44, 88, 160))
    shape(lambda m: cv2.rectangle(m, (cx + 120, 310), (cx + 170, 560), 255, -1), (60, 120, 200), (44, 88, 160))
    # the neck a little darker than the face (the default figure's own colours kept as they were)
    neck = (((178, 200, 238), (150, 168, 214)) if skin == ((190, 212, 246), (160, 180, 226))
            else tuple(tuple(max(0, c - 10) for c in t) for t in skin))
    shape(lambda m: cv2.rectangle(m, (cx - 26, 250), (cx + 26, 310), 255, -1), *neck)
    shape(lambda m: cv2.ellipse(m, (cx, 170), (100, 118), 0, 0, 360, 255, -1), *skin)
    shape(lambda m: cv2.ellipse(m, (cx, 120), (112, 82), 0, 180, 360, 255, -1), (60, 50, 120), (44, 36, 92))
    for ex in (cx - 40, cx + 40):
        cv2.ellipse(img, (ex, 180), (15, 22), 0, 0, 360, (70, 60, 40, 255), -1, cv2.LINE_AA)
        cv2.ellipse(img, (ex, 180), (15, 22), 0, 0, 360, ink, 2, cv2.LINE_AA)
        cv2.circle(img, (ex - 5, 172), 5, (255, 255, 255, 255), -1, cv2.LINE_AA)
    cv2.line(img, (cx - 14, 236), (cx + 14, 236), (60, 60, 150, 255), 3, cv2.LINE_AA)
    return img


@pytest.fixture(scope="session")
def figure(tmp_path_factory):
    d = tmp_path_factory.mktemp("figure")
    p = d / "image.png"
    cv2.imwrite(str(p), draw_figure())
    return p


@pytest.fixture(scope="session")
def draft(figure, tmp_path_factory):
    """The figure's subject file as auto_parts.py drafts it, without hints."""
    d = tmp_path_factory.mktemp("draft")
    r = subprocess.run([sys.executable, str(SCRIPTS / "auto_parts.py"), str(figure), str(d / "subject.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in (0, 1), r.stderr[-400:]
    return d / "subject.json"
