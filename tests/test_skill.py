"""The skill's tests: its packaging, its style files, its scripts, its tools, and one figure through the whole
workflow. Run from the repository's root: python -m pytest -q tests"""
import json
import re
import subprocess
import sys

import numpy as np
import pytest

from conftest import ROOT, SCRIPTS, SKILL

import cv2  # noqa: E402

PY = sys.executable


def run(script, *args):
    r = subprocess.run([PY, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None)


# ---------------------------------------------------------------------------------------------------------- packaging

def test_skill_frontmatter():
    yaml = pytest.importorskip("yaml")
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md starts with a YAML frontmatter"
    # a strict parser, as the agents' skill loaders use: an unquoted value holding ": " does not load
    front = yaml.safe_load(m.group(1))
    assert front["name"] == SKILL.name and re.fullmatch(r"[a-z0-9-]{1,64}", front["name"])
    assert 0 < len(front["description"]) <= 1024
    assert "<" not in front["description"] and ">" not in front["description"]
    assert len(front.get("compatibility", "")) <= 500
    assert all(isinstance(v, str) for v in front.get("metadata", {}).values())
    assert len(text.splitlines()) < 500


def test_plugin_manifest():
    pj = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    for path in pj["skills"]:
        assert (ROOT / path / "SKILL.md").is_file()
    if "icon" in pj:
        assert (ROOT / pj["icon"]).is_file()


def test_skill_folder_carries_the_licence():
    """The skill is often copied on its own, without the repository round it: its folder keeps the licence."""
    assert (SKILL / "LICENSE").read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_references_linked_from_skill_exist():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for rel in set(re.findall(r"\]\((references/[^)#]+)\)", text)):
        assert (SKILL / rel).is_file(), rel


def test_no_personal_data():
    """Nothing of the people who made it: no paths on their machines, no keys, no addresses."""
    bad = [re.compile(p) for p in (r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)", r"[\\/]Users[\\/]", r"[\\/]home[\\/]\w",
                                   r"\bsk-[A-Za-z0-9_-]{16,}", r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
                                   r"(?i)api[_-]?key\s*[:=]\s*['\"]?\w{12,}")]
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts or ".git" in p.parts or p.suffix not in (
                ".py", ".md", ".json", ".txt", ".yaml", ".yml", ".toml", ""):
            continue
        if p == ROOT / "tests" / "test_skill.py":
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if any(b.search(line) for b in bad):
                hits.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:80]}")
    assert not hits, "\n".join(hits)


# ------------------------------------------------------------------------------------------------------------ styles

def test_every_style_loads():
    from _style import ENGINES, load_style
    styles = sorted((SKILL / "styles").glob("*.json"))
    assert len(styles) >= 30
    for p in styles:
        st = load_style(p)
        assert st["engine"] in ENGINES
        assert st.get("id") == p.stem, p.name
        assert st.get("name") and st.get("summary"), p.name


def test_presets_list_every_style():
    text = (SKILL / "references" / "presets.md").read_text(encoding="utf-8")
    for p in (SKILL / "styles").glob("*.json"):
        assert f"`{p.stem}`" in text, p.stem


# ----------------------------------------------------------------------------------------------------------- scripts

@pytest.mark.parametrize("script", sorted(p.name for p in SCRIPTS.glob("*.py") if not p.name.startswith("_")))
def test_script_help(script):
    r = subprocess.run([PY, str(SCRIPTS / script), "--help"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    assert r.returncode == 0, r.stderr[-400:]


# ------------------------------------------------------------------------------------------------------------- tools

def test_adjectives_match_longest_first():
    from _adjectives import match
    assert match("softer shadows please") == ["softer_shadows"]
    assert set(match("陰影柔一點，更鮮豔，線粗一點")) == {"softer_shadows", "more_vivid", "thicker_lines"}
    assert set(match("線を太く、パステル")) == {"thicker_lines", "pastel"}
    assert match("nothing here") == []


def test_adjective_entries_well_formed():
    from _adjectives import ADJECTIVES
    for k, e in ADJECTIVES.items():
        assert e["words"] and e["measure"]
        for eng, changes in e.items():
            if eng in ("words", "measure"):
                continue
            for ch in changes:
                assert ch[0] in ("add", "mul", "set", "post", "unpost"), (k, ch)
                if ch[0] in ("add", "mul"):
                    assert len(ch) == 5 and ch[3] <= ch[4], (k, ch)


def test_tweak_style(tmp_path):
    out = tmp_path / "out.json"
    r, _ = run("tweak_style.py", "tv-cel", out, "more vivid", "--steps", "20")
    assert r.returncode == 0
    assert json.loads(out.read_text(encoding="utf-8"))["palette"]["chroma"] <= 1.6   # held within the table's bound
    r, d = run("tweak_style.py", "deai-light", tmp_path / "o2.json", "more blush")
    assert "more_blush" in d["not_for_this_engine"]
    r, _ = run("tweak_style.py", "tv-cel", tmp_path / "o3.json", "bigger eyes")
    assert r.returncode == 1                                                           # the design is not the finish


def test_fit_nudge():
    import fit_style
    st = {"shading": {"follow": "drawn"}, "lines": {"colour": "own"}, "palette": {"chroma": 1.0}}
    step = {f: 1.0 for f in fit_style.FINISH}
    moved = {p: n for p, o, n in fit_style.nudge(st, {"chroma.median": 20.0, "line_width": 1.0, "texture": 0.6},
                                                 {"chroma.median": 10.0, "line_width": 0.5, "texture": 0.3}, step)}
    assert moved["palette.chroma"] > 1.0 and moved["lines.grow"] > 0 and moved["texture.grain"] > 0
    assert fit_style.nudge(st, {"chroma.median": 20.0}, {"chroma.median": 21.0}, step) == []   # 5 % off: left alone


def test_png_note(tmp_path):
    p = tmp_path / "a.png"
    img = (np.random.default_rng(1).random((20, 30, 4)) * 255).astype(np.uint8)
    cv2.imwrite(str(p), img)
    for note in ("AI-assisted: test", "AI 輔助：原圖由影像模型生成（処理済み）"):
        r, _ = run("png_note.py", p, note)
        assert r.returncode == 0
        _, d = run("png_note.py", p, "--read")
        assert d["notes"]["Comment"] == note                     # outside Latin-1 too (an iTXt chunk)
    assert np.array_equal(cv2.imread(str(p), cv2.IMREAD_UNCHANGED), img)              # pixels untouched


def test_scene_kinds():
    from scene_subject import kind_of_area
    assert kind_of_area([62, -1, -38], 0.0, 0.3, True) == "sky"
    assert kind_of_area([60, -12, 30], 0.3, 0.7, False) == "foliage"
    assert kind_of_area([74, 8, 27], 0.6, 1.0, False) == "ground"
    assert kind_of_area([50, -5, -30], 0.6, 0.95, False) == "water"
    assert kind_of_area([45, 0, -10], 0.6, 0.95, False) != "water"       # night-tinted stone is not water


def test_duotone_separation():
    import _duotone
    paper = np.array([1.0, 1.0, 1.0], np.float32)
    inks = [_duotone.colour_lab([14, 0, 0]), _duotone.colour_lab([50, 66, 46])]
    T = np.array([_duotone.transmit(c) for c in inks], np.float32)
    cov = _duotone.separate(np.array([[95, 0, 0], [20, 0, 0], [52, 60, 40]], np.float32), T, paper)
    assert cov[0].max() < 0.15 and cov[1][0] > 0.7 and cov[2][1] > 0.7 and cov[2][0] < 0.3


def test_two_colour_region_doubt():
    """A region of two materials (a gap in a line) is named in a doubt; a garment's lit and shaded tones are not."""
    import auto_parts as A
    from _core import lab
    h, w = 200, 300
    img = np.zeros((h, w, 3), np.float32)
    reg = np.zeros((h, w), np.int32)
    reg[:, :150] = 1                                            # orange over navy, no line between
    img[:100, :150] = (200 / 255, 120 / 255, 60 / 255)
    img[100:, :150] = (52 / 255, 64 / 255, 92 / 255)
    reg[:, 150:] = 2                                            # orange lit and shaded
    img[:, 150:225] = (200 / 255, 120 / 255, 60 / 255)
    img[:, 225:] = (160 / 255, 88 / 255, 44 / 255)
    L = lab(img)
    core = np.ones((h, w), bool)
    st = A.region_stats(reg, L, core)
    parts = [{"name": "a", "kind": "cloth", "regions": [1]}, {"name": "b", "kind": "cloth", "regions": [2]}]
    out = A.two_colour_regions(reg, L, core, st, parts, {"area": float(h * w)})
    assert len(out) == 1 and out[0].startswith("region 1 ")


# ------------------------------------------------------------------------------------------------ the whole workflow

# the hints, in the drawn figure's pixels: one point on each material's lit side and one in its shade
HINTS = {
    "eyes": [[178, 150, 222, 210], [258, 150, 302, 210]],
    "mouth": [222, 230, 258, 242],
    "parts": [
        {"name": "hair", "kind": "hair", "at": [[240, 70]]},
        {"name": "skin", "kind": "skin", "at": [[190, 255]]},
        {"name": "jacket", "kind": "cloth", "at": [[200, 450], [320, 450], [85, 430], [400, 430]]},
        {"name": "trousers", "kind": "cloth-dark", "at": [[180, 700], [300, 700]]},
        {"name": "shoes", "kind": "cloth-dark", "at": [[175, 848], [305, 848]]},
    ],
}

# where each part must end up: both the lit and the shaded side of every piece
WHERE = (("jacket", (200, 450)), ("jacket", (320, 450)), ("jacket", (85, 430)), ("jacket", (112, 430)),
         ("jacket", (375, 430)), ("jacket", (400, 430)), ("trousers", (180, 700)), ("trousers", (225, 700)),
         ("trousers", (260, 700)), ("trousers", (310, 760)), ("shoes", (175, 848)), ("shoes", (220, 848)),
         ("shoes", (270, 848)), ("shoes", (320, 848)), ("skin", (200, 260)), ("hair", (240, 70)))


def test_workflow(figure, tmp_path):
    from _core import load_rgba
    from _style import load_subject
    from parts import load_or_build

    r, d = run("check_input.py", figure)
    assert r.returncode in (0, 1) and "cel" in json.dumps(d)

    # a figure under 2000 px is enlarged first, as SKILL.md says; the hints move with it
    image = tmp_path / "image.png"
    r, d = run("prep.py", figure, image, "--scale", "2")
    assert r.returncode == 0, r.stderr[-400:]
    x0, y0 = d["box"][:2]

    def at(x, y):
        return [(x - x0) * 2, (y - y0) * 2]

    # the draft: the face, the hair and the skin found; the trousers and the shoes run together where the line between
    # them is dark on dark cloth
    r, d = run("auto_parts.py", image, tmp_path / "draft.json", "--upscaled", "2")
    assert r.returncode in (0, 1), r.stderr[-400:]
    assert {"skin", "hair", "eyes"} <= {p["kind"] for p in d["parts"]}

    # the hints part them, each material whole: its lit and shaded tones together, whichever side was pointed at
    hints = {"eyes": [at(*b[:2]) + at(*b[2:]) for b in HINTS["eyes"]],
             "mouth": at(*HINTS["mouth"][:2]) + at(*HINTS["mouth"][2:]),
             "parts": [{**p, "at": [at(*q) for q in p["at"]]} for p in HINTS["parts"]]}
    hp = tmp_path / "hints.json"
    hp.write_text(json.dumps(hints), encoding="utf-8")
    r, d = run("auto_parts.py", image, tmp_path / "subject.json", "--upscaled", "2", "--hints", hp)
    assert r.returncode in (0, 1), r.stderr[-400:]
    sj = load_subject(tmp_path / "subject.json")
    _, _, parts = load_or_build(sj)
    names = [""] + [p["name"] for p in sj["parts"]]
    wrong = []
    for name, xy in WHERE:
        x, y = at(*xy)
        if names[parts[y, x]] != name:
            wrong.append((name, xy, names[parts[y, x]]))
    assert not wrong, wrong

    # the finish: the same figure, the same size, nothing added round it, and checked
    src, alpha = load_rgba(image)
    for style in ("tv-cel", "deai-light", "watercolour", "pop-art-dots", "stained-glass", "charcoal", "soft-pastel"):
        out = tmp_path / f"{style}.png"
        r, d = run("refinish.py", tmp_path / "subject.json", style, out)
        assert r.returncode in (0, 1), (style, r.stderr[-600:])
        res, res_alpha = load_rgba(out)
        assert res.shape == src.shape, style
        assert np.mean(np.abs(res_alpha - alpha) > 0.5) < 0.01, style
        if style in ("tv-cel", "deai-light"):
            assert d["check"]["verdict"] in ("pass", "warn", "fail")

    # the styles that grow the picture: larger on every side, the figure inside unchanged in place
    for style in ("sticker", "neon-sign"):
        out = tmp_path / f"{style}.png"
        r, d = run("refinish.py", tmp_path / "subject.json", style, out)
        assert r.returncode in (0, 1), (style, r.stderr[-600:])
        res, res_alpha = load_rgba(out)
        pad = d["pad"]
        assert res.shape[0] == src.shape[0] + 2 * pad and res.shape[1] == src.shape[1] + 2 * pad, style
        inner = res_alpha[pad:pad + src.shape[0], pad:pad + src.shape[1]]
        assert np.mean((inner > 0.5) < (alpha > 0.5)) < 0.01, style        # the figure is still all there

    # paper cut: no drawn lines, the silhouette smoothed a little
    r, d = run("refinish.py", tmp_path / "subject.json", "paper-cut", tmp_path / "paper.png")
    assert r.returncode in (0, 1), r.stderr[-600:]
    res, res_alpha = load_rgba(tmp_path / "paper.png")
    assert res.shape == src.shape
    assert np.mean((res_alpha > 0.5) != (alpha > 0.5)) < 0.02

    # a recipe: watercolour on the clothes over a TV cel base, a screentone multiplied on the trousers
    rp = tmp_path / "recipe.json"
    rp.write_text(json.dumps({"format": "refinish-recipe/1", "subject": "subject.json", "base": "tv-cel",
                              "layers": [{"style": "watercolour", "where": ["cloth", "cloth-dark"], "feather": 2},
                                         {"style": "manga-screentone", "where": ["trousers"], "blend": "multiply",
                                          "opacity": 0.6}]}), encoding="utf-8")
    r, d = run("recipe.py", rp, tmp_path / "mix.png")
    assert r.returncode == 0, r.stderr[-600:]
    assert [x["style"] for x in d["finishes"]] == ["tv-cel", "watercolour", "manga-screentone"]
    mix, _ = load_rgba(tmp_path / "mix.png")
    cel, _ = load_rgba(tmp_path / "tv-cel.png")
    x, y = at(240, 170)                                              # the face: the base finish, untouched
    assert np.abs(mix[y - 3:y + 4, x - 3:x + 4] - cel[y - 3:y + 4, x - 3:x + 4]).max() < 0.02
    rp.write_text(json.dumps({"format": "refinish-recipe/1", "subject": "subject.json", "base": "tv-cel",
                              "layers": [{"style": "watercolour", "where": ["no-such-part"]}]}), encoding="utf-8")
    r, _ = run("recipe.py", rp, tmp_path / "bad.png")
    assert r.returncode == 2 and "no-such-part" in r.stdout + r.stderr


def test_repair(figure, tmp_path):
    """A fringe, specks and a line gap made on purpose are found and fixed; a clean picture is left alone."""
    from _core import load_rgba
    im = cv2.imread(str(figure), cv2.IMREAD_UNCHANGED)
    clean = tmp_path / "clean.png"
    cv2.imwrite(str(clean), im)
    r, d = run("repair.py", clean, tmp_path / "clean_out.png", "--fix", "halo,specks")
    assert r.returncode == 0, r.stderr[-400:]
    assert not d["repairs"]["halo"]["found"]
    assert d["repairs"]["specks"]["found"] == 0
    bad = im.copy()
    a = bad[..., 3]
    rim = (cv2.dilate((a > 127).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & (a < 128)
    bad[rim, :3] = 255
    bad[rim, 3] = 160                                                # a white fringe from a light background
    rng = np.random.default_rng(1)
    spots = [(200, 450), (320, 450), (180, 700), (300, 700)]         # flat cloth
    for x, y in spots:
        bad[y:y + 3, x:x + 3, :3] = rng.integers(0, 255, 3)
    p = tmp_path / "bad.png"
    cv2.imwrite(str(p), bad)
    r, d = run("repair.py", p, tmp_path / "fixed.png", "--fix", "halo,specks")
    assert r.returncode == 0, r.stderr[-400:]
    assert d["repairs"]["halo"]["found"] and d["repairs"]["halo"]["fringe"] == "light"
    assert d["repairs"]["specks"]["found"] >= len(spots)
    fixed, _ = load_rgba(tmp_path / "fixed.png")
    src, _ = load_rgba(figure)
    for x, y in spots:
        assert np.abs(fixed[y + 1, x + 1] - src[y + 1, x + 1]).max() < 0.08


# ------------------------------------------------------------------------------------------ a darker skin kept as it is

def test_darker_skin_kept(tmp_path):
    """The styles with a skin convention (the woodblock's pale skin, manga's paper skin, pop art's red and yellow dots)
    keep a darker skin's own tone, print no box round the features, and the look checks find nothing to flag."""
    from conftest import draw_figure
    from _core import load_rgba, lab
    src_p = tmp_path / "dark.png"
    cv2.imwrite(str(src_p), draw_figure(skin=((60, 90, 140), (44, 66, 110))))     # BGR: a brown skin, L about 42
    image = tmp_path / "image.png"
    r, d = run("prep.py", src_p, image, "--scale", "2")
    assert r.returncode == 0, r.stderr[-400:]
    x0, y0 = d["box"][:2]

    def at(x, y):
        return [(x - x0) * 2, (y - y0) * 2]

    hints = {"eyes": [at(*b[:2]) + at(*b[2:]) for b in HINTS["eyes"]],
             "mouth": at(*HINTS["mouth"][:2]) + at(*HINTS["mouth"][2:]),
             "parts": [{**p, "at": [at(*q) for q in p["at"]]} for p in HINTS["parts"]]}
    hp = tmp_path / "hints.json"
    hp.write_text(json.dumps(hints), encoding="utf-8")
    r, _ = run("auto_parts.py", image, tmp_path / "subject.json", "--upscaled", "2", "--hints", hp)
    assert r.returncode in (0, 1), r.stderr[-400:]
    src, _ = load_rgba(image)
    x, y = at(205, 140)                                              # the lit forehead, away from the features
    L_src = float(np.median(lab(src[y - 8:y + 9, x - 8:x + 9])[..., 0]))
    for style in ("ukiyo-e-woodblock", "manga-screentone", "pop-art-dots", "sepia"):
        out = tmp_path / f"{style}.png"
        r, d = run("refinish.py", tmp_path / "subject.json", style, out)
        assert r.returncode in (0, 1), (style, r.stderr[-600:])
        res, _ = load_rgba(out)
        L_res = float(np.mean(lab(cv2.GaussianBlur(res, (0, 0), 6))[y - 8:y + 9, x - 8:x + 9, 0]))
        assert L_res < L_src + 25, (style, L_src, L_res)            # not printed pale
        assert d["check"]["verdict"] in ("pass", "warn", "fail"), style   # the duotones are checked too
        flagged = [f for f in d["check"].get("findings", []) if f[:2] in ("O7", "O8")]
        assert not flagged, (style, flagged)


# ------------------------------------------------------------------------------------------ a figure cut out of a scene

def test_cutout(tmp_path):
    """A drawn figure laid on a textured wall comes back out from a rough outline: the edge found by colour, the gap
    between the legs kept as figure until a hole is drawn in it, and the background written with the figure's place
    filled from the wall round it."""
    from conftest import draw_figure
    fig = draw_figure()
    h, w = fig.shape[:2]
    rng = np.random.default_rng(1)
    wall = np.array((150, 205, 120), np.float32)                     # BGR: a grey-green wall
    scene = wall + rng.normal(0, 6, (h, w, 3))
    a = fig[..., 3:4].astype(np.float32) / 255
    cv2.imwrite(str(tmp_path / "scene.png"), np.clip(fig[..., :3] * a + scene * (1 - a), 0, 255).astype(np.uint8))
    truth = fig[..., 3] > 127
    grown = cv2.dilate(truth.astype(np.uint8), np.ones((17, 17), np.uint8))     # the outline 8 px outside the edge
    cnt, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    outline = cv2.approxPolyDP(max(cnt, key=cv2.contourArea), 2, True)[:, 0].tolist()
    cx = w // 2
    gap = np.zeros((h, w), bool)
    gap[600:812, cx - 6:cx + 7] = True                               # between the trouser legs, above the shoes
    results = {}
    for name, extra in (("plain", {}), ("hole", {"holes": [[[cx - 3, 604], [cx + 3, 604], [cx + 3, 808],
                                                             [cx - 3, 808]]]})):
        op = tmp_path / f"{name}.json"
        op.write_text(json.dumps({"outline": [outline], "band": 16, **extra}), encoding="utf-8")
        r, d = run("cutout.py", tmp_path / "scene.png", op, tmp_path / name)
        assert r.returncode in (0, 1), r.stderr[-600:]
        out = cv2.imread(str(tmp_path / name / "figure.png"), cv2.IMREAD_UNCHANGED)
        assert out.shape == (h, w, 4)
        results[name] = out[..., 3] > 127
        cut = results[name] & ~gap
        t = truth & ~gap
        assert (cut & t).sum() / (cut | t).sum() > 0.97, name           # the edge found off the gap
    assert results["plain"][gap].mean() > 0.5                         # a gap inside the outline stays without a hole
    assert results["hole"][gap].mean() < 0.2                          # and comes out with one
    bg = cv2.imread(str(tmp_path / "hole" / "background.png")).astype(np.float32)
    inside = cv2.erode(truth.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    assert np.abs(bg[inside] - wall).mean() < 20                      # the figure's place filled with the wall


# ------------------------------------------------------------------------------- nothing done, or skipped, in silence

def test_sixteen_bit_png(tmp_path):
    """A 16-bit picture is read at its own depth (it once came out white: its values divided by 255)."""
    from _core import load_rgba
    im = np.zeros((4, 4, 4), np.uint16)
    im[..., :3], im[..., 3] = 32768, 65535
    cv2.imwrite(str(tmp_path / "sixteen.png"), im)
    rgb_, a_ = load_rgba(tmp_path / "sixteen.png")
    assert abs(float(rgb_[0, 0, 0]) - 0.5) < 0.01 and abs(float(a_[0, 0]) - 1.0) < 1e-6


def test_composite_keeps_alpha_and_reports_writes(tmp_path):
    """A half-opaque layer is laid at half (a glow or a shadow must not vanish), the output's folder is made, and a file
    that cannot be written is an error, never a reported success."""
    cv2.imwrite(str(tmp_path / "bg.png"), np.full((100, 200, 3), 200, np.uint8))
    lay = np.zeros((100, 100, 4), np.uint8)
    lay[..., 2], lay[..., 3] = 255, 128
    cv2.imwrite(str(tmp_path / "half.png"), lay)
    scene = {"frame": [200, 100], "background": {"image": "bg.png"},
             "layers": [{"image": "half.png", "place": [50, 100, 1.0]}]}
    (tmp_path / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    out = tmp_path / "new" / "frame.png"
    r, _ = run("composite.py", tmp_path / "scene.json", out, "--raw")
    assert r.returncode == 0 and out.is_file(), r.stderr[-300:]
    b, g, red = (int(v) for v in cv2.imread(str(out))[50, 100])
    assert abs(red - 228) <= 3 and abs(g - 100) <= 3 and abs(b - 100) <= 3
    # asked for, a generator's faint halo is cleared: here the whole layer, which has no opaque figure
    scene["layers"][0]["clear_halo"] = True
    (tmp_path / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    r, _ = run("composite.py", tmp_path / "scene.json", tmp_path / "cleared.png", "--raw")
    assert tuple(int(v) for v in cv2.imread(str(tmp_path / "cleared.png"))[50, 100]) == (200, 200, 200)
    r, _ = run("composite.py", tmp_path / "scene.json", tmp_path / "frame.unknown")
    assert r.returncode == 2 and not (tmp_path / "frame.unknown").exists()


def test_mist_laid_once():
    """The mist follows the curve style-format.md gives, 1 - (1 - k)²: `amount` 0.5 leaves a day sky 0.75 paper (a
    plain blend would give 0.5, a second blend over the curve 0.9375)."""
    import _texture as tx
    from _core import Units
    from _scene import mist
    h, w = 200, 300
    parts = np.full((h, w), 2, np.int32)
    parts[:100] = 1
    subject = {"parts": [{"name": "sky", "kind": "sky"}, {"name": "ground", "kind": "ground"}]}
    img = np.full((h, w, 3), 0.6, np.float32)
    out = mist(img, parts, subject, Units(np.ones((h, w), np.float32)), {"amount": 0.5, "bands": 0.0})
    paper = np.asarray(tx.sheet_rgb("xuan"), np.float32)
    k = float(np.mean((out[40, 150] - img[40, 150]) / (paper - img[40, 150])))
    assert abs(k - 0.75) < 0.02, k


def test_hour_refused_where_the_size_changes(draft, tmp_path):
    """The pixel, sticker and neon finishes change the picture's size: --hour is refused, not skipped."""
    for style in ("pixel-character", "sticker", "neon-sign"):
        out = tmp_path / f"{style}.png"
        r, _ = run("refinish.py", draft, style, out, "--hour", "night")
        assert r.returncode == 2 and "--hour" in r.stderr and not out.exists(), (style, r.stderr[-300:])


def test_exit_codes_follow_the_checks(draft, tmp_path):
    """refinish.py exits 1 on a FAIL, as SKILL.md says, and check_output.py --style gives the same verdict."""
    for style in ("pop-art-dots", "duotone-navy"):
        out = tmp_path / f"{style}.png"
        r, d = run("refinish.py", draft, style, out)
        assert r.returncode == (1 if d["check"]["verdict"] == "fail" else 0), (style, d["check"])
        r2, d2 = run("check_output.py", draft, out, "--style", style)
        assert (r2.returncode, d2["verdict"]) == (r.returncode, d["check"]["verdict"]), (style, d2["verdict"])
