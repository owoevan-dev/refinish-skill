"""Where hair meets skin, and how strong a colour card's shadows and lights come out."""
import json
import subprocess
import sys

import cv2
import numpy as np
import pytest

from conftest import SCRIPTS, SKILL, draw_figure

HAIR, SKIN = (0.75, 0.73, 0.72), (0.97, 0.86, 0.78)
HAIR_PAINT, SKIN_PAINT = (0.30, 0.20, 0.15), (0.97, 0.88, 0.80)


def border_scene(ramp):
    """Hair on the left, skin on the right, meeting over `ramp` pixels in the source and at x = 100 in the part map."""
    from _core import Units
    h, w = 1000, 200                                    # (a figure this tall has one pixel to the style unit)
    x = np.arange(w, dtype=np.float32)
    t = (np.clip((x - (100 - ramp / 2)) / ramp, 0, 1) if ramp else (x >= 100).astype(np.float32))[None, :, None]
    img = np.array(HAIR, np.float32) * (1 - t) + np.array(SKIN, np.float32) * t
    img = np.repeat(img, h, axis=0).astype(np.float32)
    hair = np.zeros((h, w), bool)
    hair[:, :100] = True
    out = np.empty((h, w, 3), np.float32)
    out[hair], out[~hair] = HAIR_PAINT, SKIN_PAINT
    return out, img, hair, ~hair, np.ones((h, w), bool), np.zeros((h, w), bool), Units(np.ones((h, w), np.float32), None)


def test_a_fringe_that_fades_in_the_source_fades_in_the_finish():
    from _cel import soft_hair_edge
    args = border_scene(8)
    res = soft_hair_edge(*args)
    row = res[500, :, 0]
    assert np.all(np.diff(row) >= -1e-3), "from the hair's paint to the skin's, with no way back"
    between = (row > HAIR_PAINT[0] + 0.05) & (row < SKIN_PAINT[0] - 0.05)
    assert between.sum() >= 2
    assert row[0] == pytest.approx(HAIR_PAINT[0]) and row[-1] == pytest.approx(SKIN_PAINT[0])


def test_a_hard_drawn_edge_stays_hard():
    from _cel import soft_hair_edge
    args = border_scene(0)
    res = soft_hair_edge(*args)
    assert np.abs(res - args[0]).max() < 0.02


def test_a_highlight_inside_the_hair_is_not_read_as_skin():
    from _cel import soft_hair_edge
    out, img, hair, skin, face, line, U = border_scene(0)
    img[480:520, 30:60] = (0.95, 0.93, 0.92)
    res = soft_hair_edge(out, img, hair, skin, face, line, U)
    assert np.array_equal(res[480:520, 30:60], out[480:520, 30:60])


def test_a_broad_shadow_on_the_skin_stays_skin():
    from _cel import soft_hair_edge
    out, img, hair, skin, face, line, U = border_scene(0)
    img[460:540, 130:190] = np.array(SKIN, np.float32) * 0.82
    res = soft_hair_edge(out, img, hair, skin, face, line, U)
    assert np.array_equal(res[460:540, 130:190], out[460:540, 130:190])


def test_a_black_line_near_the_border_does_not_lighten_the_hair():
    from _cel import soft_hair_edge
    out, img, hair, skin, face, line, U = border_scene(0)
    img[:, 94:96] = (0.03, 0.03, 0.03)
    res = soft_hair_edge(out, img, hair, skin, face, line, U)
    assert np.abs(res[:, 80:98] - out[:, 80:98]).max() < 0.02


def test_hair_beside_a_collar_is_no_fringe():
    from _cel import soft_hair_edge
    out, img, hair, skin, face, line, U = border_scene(0)
    skin = skin.copy()
    skin[300:700] = False                               # (here the hair meets another part)
    img[300:700, 100:] = (0.1, 0.2, 0.5)
    res = soft_hair_edge(out, img, hair, skin, face, line, U)
    assert np.array_equal(res[400:600], out[400:600])


def test_dark_hair_is_a_hard_edge_as_drawn():
    from _cel import soft_hair_edge
    out, img, hair, skin, face, line, U = border_scene(8)
    img[hair] = (0.08, 0.07, 0.09)
    assert soft_hair_edge(out, img, hair, skin, face, line, U) is out


def test_only_the_face_is_touched():
    from _cel import soft_hair_edge
    out, img, hair, skin, face, line, U = border_scene(24)
    res = soft_hair_edge(out, img, hair, skin, np.zeros_like(face), line, U)
    assert res is out


def test_hair_and_skin_of_one_colour_are_left_alone():
    from _cel import soft_hair_edge
    out, img, hair, skin, face, line, U = border_scene(24)
    img[:] = SKIN
    assert np.array_equal(soft_hair_edge(out, img, hair, skin, face, line, U), out)


# --------------------------------------------------------------------------------------------------------- a card's tones

def run(script, *args, cwd):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode in (0, 1) and "Traceback" not in r.stderr, r.stderr[-600:]
    return r


def recoloured_hair(tmp_path, paint_hair):
    """The drawn figure with its hair repainted by `paint_hair`, carded dark. The hair's lightness before and after."""
    fig = draw_figure()
    hair = (np.abs(fig[..., :3].astype(np.int32) - (60, 50, 120)).sum(2) < 6) | (
        np.abs(fig[..., :3].astype(np.int32) - (44, 36, 92)).sum(2) < 6)
    assert hair.sum() > 3000
    paint_hair(fig, hair)
    cv2.imwrite(str(tmp_path / "image.png"), fig)
    run("auto_parts.py", "image.png", "subject.json", cwd=tmp_path)
    (tmp_path / "card.json").write_text(json.dumps({"format": "refinish-palette/1", "name": "dark",
                                                    "kinds": {"hair": "#4a3024"}}), encoding="utf-8")
    run("palette.py", "apply", "subject.json", "card.json", "carded.json", cwd=tmp_path)
    run("refinish.py", "carded.json", SKILL / "styles" / "film-everyday-cel.json", "out.png", cwd=tmp_path)
    core = cv2.erode(hair.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    light = lambda im: cv2.cvtColor(im[..., :3], cv2.COLOR_BGR2LAB)[..., 0][core].astype(np.float32) * 100 / 255
    return light(fig), light(cv2.imread(str(tmp_path / "out.png"), cv2.IMREAD_UNCHANGED))


def test_a_faint_sheen_on_pale_hair_does_not_turn_into_blotches(tmp_path):
    def pale(fig, hair):
        noise = cv2.GaussianBlur(np.random.default_rng(3).normal(0, 1, hair.shape).astype(np.float32), (0, 0), 7)
        fig[hair] = np.clip(205 + noise[hair] / noise.std() * 3, 0, 255)[:, None].astype(np.uint8)
    before, after = recoloured_hair(tmp_path, pale)
    spread = lambda v: float(np.percentile(v, 97) - np.percentile(v, 3))
    assert spread(after) < 10.0, (spread(before), spread(after))         # (it was 33 before the card kept the drawn step)


def test_a_strong_drawn_highlight_survives_a_dark_card(tmp_path):
    def glossy(fig, hair):
        fig[hair] = 120
        ys, xs = np.nonzero(hair)
        band = hair & (np.abs(np.arange(hair.shape[0])[:, None] - (ys.min() + 34)) < 7)
        fig[band] = 235
    _, after = recoloured_hair(tmp_path, glossy)
    assert np.percentile(after, 97) - np.median(after) > 8.0
