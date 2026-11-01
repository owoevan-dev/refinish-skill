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

SKILLS = sorted(p.parent for p in (ROOT / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_frontmatter(skill):
    yaml = pytest.importorskip("yaml")
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md starts with a YAML frontmatter"
    # a strict parser, as the agents' skill loaders use: an unquoted value holding ": " does not load
    front = yaml.safe_load(m.group(1))
    assert front["name"] == skill.name and re.fullmatch(r"[a-z0-9-]{1,64}", front["name"])
    assert 0 < len(front["description"]) <= 1024
    assert "<" not in front["description"] and ">" not in front["description"]
    assert len(front.get("compatibility", "")) <= 500
    assert all(isinstance(v, str) for v in front.get("metadata", {}).values())
    assert len(text.splitlines()) < 500


def test_plugin_manifest():
    pj = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    for path in pj["skills"]:
        assert (ROOT / path / "SKILL.md").is_file()
    assert sorted((ROOT / p).resolve() for p in pj["skills"]) == [s.resolve() for s in SKILLS]
    if "icon" in pj:
        assert (ROOT / pj["icon"]).is_file()


def square_icon(path):
    """An icon a listing takes: square and at least 48 pixels, raster or SVG."""
    if path.suffix == ".svg":
        w, h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', path.read_text(encoding="utf-8")).groups())
    else:
        h, w = cv2.imread(str(path), cv2.IMREAD_UNCHANGED).shape[:2]
    return w == h >= 48


def test_codex_listing():
    """Codex reads its own manifest and marketplace: the same plugin as Claude's, every image it names, and the
    listing's limits (a name and subtitle of 30 characters, up to three prompts of 128)."""
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    for key in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords"):
        assert codex[key] == claude[key], key
    ui = codex["interface"]
    assert len(ui["displayName"]) <= 30 and len(ui["shortDescription"]) <= 30 and len(ui["longDescription"]) <= 4000
    assert len(ui["defaultPrompt"]) <= 3 and all(len(p) <= 128 for p in ui["defaultPrompt"])
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", ui["brandColor"])
    assert square_icon(ROOT / ui["composerIcon"]) and square_icon(ROOT / ui["logo"])
    assert all((ROOT / p).is_file() for p in ui["screenshots"])
    market = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    claude_market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert market["name"] == claude_market["name"] and [p["name"] for p in market["plugins"]] == [codex["name"]]


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_carries_its_codex_icons(skill):
    """The skill's own Codex metadata travels with the folder: its icons are inside it, the brand's own."""
    yaml = pytest.importorskip("yaml")
    ui = yaml.safe_load((skill / "agents" / "openai.yaml").read_text(encoding="utf-8"))["interface"]
    for key, brand in (("icon_small", "icon-small.svg"), ("icon_large", "icon-512.png")):
        assert (skill / ui[key]).read_bytes() == (ROOT / "assets" / "brand" / brand).read_bytes(), key


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_folder_carries_the_licence(skill):
    """The skill is often copied on its own, without the repository round it: its folder keeps the licence."""
    assert (skill / "LICENSE").read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(encoding="utf-8")


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_references_linked_from_skill_exist(skill):
    """Every page a skill links to is there, its own references and its neighbour's alike."""
    for page in [skill / "SKILL.md", *sorted((skill / "references").glob("*.md"))]:
        for rel in set(re.findall(r"\]\(((?:\.\./)*[\w./-]+\.md)(?:#[^)]*)?\)", page.read_text(encoding="utf-8"))):
            assert (page.parent / rel).is_file(), (page.name, rel)


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

    # the hints part them, each material whole: its lit and shaded tones together, whichever side was pointed at (and
    # a part's prop flag reaches the subject; the shoes stand in for a held thing here)
    hints = {"eyes": [at(*b[:2]) + at(*b[2:]) for b in HINTS["eyes"]],
             "mouth": at(*HINTS["mouth"][:2]) + at(*HINTS["mouth"][2:]),
             "parts": [{**p, "at": [at(*q) for q in p["at"]], **({"prop": True} if p["name"] == "shoes" else {})}
                       for p in HINTS["parts"]]}
    hp = tmp_path / "hints.json"
    hp.write_text(json.dumps(hints), encoding="utf-8")
    r, d = run("auto_parts.py", image, tmp_path / "subject.json", "--upscaled", "2", "--hints", hp)
    assert r.returncode in (0, 1), r.stderr[-400:]
    sj = load_subject(tmp_path / "subject.json")
    assert [p["name"] for p in sj["parts"] if p.get("prop")] == ["shoes"]
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


def test_hidden_colour_changes_nothing(tmp_path):
    """The colour a file keeps under full transparency is hidden: two files that differ only there give the same
    finish (once, black and magenta there moved 58,934 visible pixels of film-everyday-cel by up to 199)."""
    import shutil
    from conftest import draw_figure
    fig = draw_figure()
    a, b = tmp_path / "black", tmp_path / "magenta"
    a.mkdir()
    cv2.imwrite(str(a / "image.png"), fig)
    r, _ = run("auto_parts.py", a / "image.png", a / "subject.json")
    assert r.returncode in (0, 1), r.stderr[-400:]
    shutil.copytree(a, b)
    fig[fig[..., 3] == 0, :3] = (255, 0, 255)
    cv2.imwrite(str(b / "image.png"), fig)
    for style in ("film-everyday-cel", "cel-90s"):
        outs = []
        for d in (a, b):
            r, _ = run("refinish.py", d / "subject.json", style, d / f"{style}.png", "--no-check")
            assert r.returncode == 0, r.stderr[-400:]
            outs.append(cv2.imread(str(d / f"{style}.png"), cv2.IMREAD_UNCHANGED).astype(int))
        seen = (outs[0][..., 3] > 0) | (outs[1][..., 3] > 0)
        assert np.abs(outs[0] - outs[1])[seen].max() <= 1, style


def test_recipe_layer_alpha():
    """A recipe's layer paints only where it has paint: transparent, it leaves the mix below; half transparent, it
    counts half (a paper cut's trimmed edge once painted the base white)."""
    from recipe import lay_over
    base = np.full((4, 4, 3), (0.16, 0.25, 0.41), np.float32)
    white = np.ones((4, 4, 3), np.float32)
    mask = np.ones((4, 4), np.float32)
    assert np.allclose(lay_over(base, white, np.zeros((4, 4), np.float32), mask, 1.0, "normal"), base)
    half = lay_over(base, white, np.full((4, 4), 0.5, np.float32), mask, 1.0, "normal")
    assert np.allclose(half, (base + white) / 2)


def test_palette_picture_must_be_read(draft, tmp_path):
    """--palette-from names a picture: one that cannot be read stops the run before any output, and a style without
    a paint palette refuses it rather than ignoring it."""
    out = tmp_path / "g.png"
    r, _ = run("refinish.py", draft, "gouache", out, "--palette-from", tmp_path / "missing.png", "--no-check")
    assert r.returncode == 2 and not out.exists() and "palette" in r.stderr
    r, _ = run("refinish.py", draft, "tv-cel", out, "--palette-from", tmp_path / "missing.png", "--no-check")
    assert r.returncode == 2 and not out.exists()


def test_bleed_from_a_flat_part():
    """repair.py's bleed fix: a flat part's colour run into its shaded neighbour is repainted (a flat part has no
    darker half, and its empty half was a NaN that matched nothing), and a clean picture is left as it is."""
    import warnings
    from _core import Units
    from repair import fix_bleed
    h, w = 1000, 300                                                  # (a unit of 1 px: the fix reaches 4 u)
    img = np.zeros((h, w, 3), np.float32)
    parts = np.zeros((h, w), np.int32)
    parts[:, :150], parts[:, 150:] = 1, 2
    img[:, :150] = (0.20, 0.55, 0.25)
    img[:500, :150] = (0.30, 0.70, 0.35)
    img[:, 150:] = (0.80, 0.15, 0.15)
    alpha = np.ones((h, w), np.float32)
    none = np.zeros((h, w), bool)
    clean = img.copy()
    run_in = np.zeros((h, w), bool)
    run_in[300:533, 147:150] = True                                   # 699 px of red run into the coat
    img[run_in] = (0.80, 0.15, 0.15)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        out, _ = fix_bleed(img, alpha, Units(alpha), parts, ["coat", "sleeve"], none, none)
        same, _ = fix_bleed(clean, alpha, Units(alpha), parts, ["coat", "sleeve"], none, none)
    assert (np.abs(out[run_in] - img[run_in]).max(axis=1) > 0.05).mean() > 0.95
    assert np.allclose(same, clean)


def test_bad_input_stops_with_a_message(draft, tmp_path):
    """Bad input ends with exit 2 and a line saying what is wrong, never a traceback; an output's missing folder is
    made."""
    lst = tmp_path / "list.json"
    lst.write_text("[]", encoding="utf-8")
    style = json.loads((SKILL / "styles" / "pixel-character.json").read_text(encoding="utf-8"))
    style["pixel"]["colours"] = 4
    px4 = tmp_path / "px4.json"
    px4.write_text(json.dumps(style), encoding="utf-8")
    for args in (("refinish.py", lst, "tv-cel", tmp_path / "a.png"), ("refinish.py", draft, lst, tmp_path / "b.png"),
                 ("recipe.py", lst, tmp_path / "c.png"),
                 ("tweak_style.py", "tv-cel", tmp_path / "t.json", "softer shadows", "--steps", "0"),
                 ("refinish.py", draft, px4, tmp_path / "d.png", "--no-check")):
        r, _ = run(*args)
        assert r.returncode == 2 and "Traceback" not in r.stderr and "error:" in r.stderr, (args[0], r.stderr[-300:])
    r, _ = run("tweak_style.py", "tv-cel", tmp_path / "new" / "dir" / "t.json", "softer shadows")
    assert r.returncode == 0 and (tmp_path / "new" / "dir" / "t.json").is_file()


def test_small_picture_paints(tmp_path):
    """A figure 180 px tall (smaller than SKILL.md advises) still paints: the strokes' spacing was once 0."""
    from conftest import draw_figure
    cv2.imwrite(str(tmp_path / "image.png"), cv2.resize(draw_figure(), (96, 180), interpolation=cv2.INTER_AREA))
    run("auto_parts.py", tmp_path / "image.png", tmp_path / "subject.json")
    r, _ = run("refinish.py", tmp_path / "subject.json", "gouache", tmp_path / "g.png", "--no-check")
    assert r.returncode == 0, r.stderr[-400:]


def test_prep_restore(figure, tmp_path):
    """prep.py --restore puts a finish of the prepped picture back on the source's canvas: the source's size, its
    figure where it was."""
    from _core import load_rgba
    r, d = run("prep.py", figure, tmp_path / "prepped.png", "--scale", "2")
    assert r.returncode == 0
    box = ",".join(str(v) for v in d["box"])
    r, _ = run("prep.py", tmp_path / "prepped.png", tmp_path / "back.png", "--restore", figure, "--box", box,
               "--scale", "2")
    assert r.returncode == 0, r.stderr[-300:]
    src, sa = load_rgba(figure)
    back, ba = load_rgba(tmp_path / "back.png")
    assert back.shape == src.shape and np.mean(np.abs(ba - sa) > 0.5) < 0.002
    r, _ = run("prep.py", figure, tmp_path / "x.png", "--restore", figure, "--box", box, "--scale", "2")
    assert r.returncode == 2                                          # a picture of another size does not go back


def test_glass_paints_features_without_lead():
    """Stained glass: two parts painted on whole glass (the skin and the white of an eye, too close in colour for the
    protected boxes to tell apart) meet on one piece, with no lead between them; a cut part is still leaded."""
    import _glass
    from _core import Units
    h, w = 160, 240
    parts = np.full((h, w), 1, np.int32)
    parts[:, 160:] = 3
    yy, xx = np.mgrid[0:h, 0:w]
    eye = (yy - 80) ** 2 + (xx - 80) ** 2 < 24 ** 2
    parts[eye] = 2
    cel = np.zeros((h, w, 3), np.float32)
    cel[parts == 1] = (0.93, 0.80, 0.74)
    cel[parts == 2] = (0.95, 0.93, 0.92)
    cel[parts == 3] = (0.25, 0.35, 0.60)
    subject = {"parts": [{"name": "skin", "kind": "skin"}, {"name": "eye", "kind": "eyes"},
                         {"name": "coat", "kind": "cloth"}]}
    alpha = np.ones((h, w), np.float32)
    style = {"glass": {"grisaille": ["skin", "eyes"]}}
    out, _ = _glass.run(subject, style, cel, alpha, parts, Units(alpha), seed=7)
    lead = (out.max(axis=2) - out.min(axis=2) < 0.08) & (out.mean(axis=2) < 0.55)   # the came: a dark neutral grey
    ring = np.abs(np.hypot(yy - 80, xx - 80) - 24) < 2.5
    assert lead[ring].mean() < 0.02, lead[ring].mean()                # no lead round the eye
    assert lead[20:140, 154:166].any(axis=1).mean() > 0.9             # the lead between skin and coat stays


def test_recheck_reads_what_the_file_shows(draft, tmp_path):
    """check_output.py --style guards the part map as refinish.py did, so a plain finish gets the same findings (on the
    draft, unguarded, it once found 9 warnings where refinish.py found 2); a file under a relight gets the part map's
    checks only (P1, P2, M1), so the night is not misread: a light coat cut by the bottom of the frame once failed O3
    there, as a dark line along the cut."""
    for style in ("tv-cel", "heavy-cel"):
        out = tmp_path / f"{style}.png"
        r1, d1 = run("refinish.py", draft, style, out)
        r2, d2 = run("check_output.py", draft, out, "--style", style)
        assert d1["guard"].get("moved_px", 0) > 0                     # the guard moves pixels on the draft
        mine = sorted(tuple(f.split(":")[0].split(" ", 2)) for f in d1["check"]["findings"])
        assert mine == sorted((f["id"], f["level"], f["part"]) for f in d2["findings"]), style
        assert r1.returncode == r2.returncode, style

    from conftest import draw_figure
    fig = draw_figure()
    coat = np.all(fig[..., :3] == (60, 120, 200), axis=2)
    shade = np.all(fig[..., :3] == (44, 88, 160), axis=2)
    fig[coat, :3], fig[shade, :3] = (226, 228, 232), (196, 200, 208)
    cv2.imwrite(str(tmp_path / "coat.png"), fig[:520])
    r, _ = run("auto_parts.py", tmp_path / "coat.png", tmp_path / "subject.json")
    assert r.returncode in (0, 1), r.stderr[-400:]
    sp = tmp_path / "subject.json"
    for style, extra in (("tv-cel-night", ()), ("tv-cel", ("--hour", "night"))):
        out = tmp_path / f"{style}{'-'.join(('',) + extra)}.png"
        r1, d1 = run("refinish.py", sp, style, out, *extra)
        r2, d2 = run("check_output.py", sp, out, "--style", style, *extra)
        assert "note" in d2 and all(f["id"] in ("P1", "P2", "M1") for f in d2["findings"]), (style, d2["findings"])
        assert d1["check"]["verdict"] != "fail" and r2.returncode == 0, (style, d2["verdict"])


def test_exit_codes_follow_the_checks(draft, tmp_path):
    """refinish.py exits 1 on a FAIL, as SKILL.md says, and check_output.py --style reaches the same verdict on these
    two (a print built on a cel finish, and a duotone)."""
    for style in ("pop-art-dots", "duotone-navy"):
        out = tmp_path / f"{style}.png"
        r, d = run("refinish.py", draft, style, out)
        assert r.returncode == (1 if d["check"]["verdict"] == "fail" else 0), (style, d["check"])
        r2, d2 = run("check_output.py", draft, out, "--style", style)
        assert (r2.returncode, d2["verdict"]) == (r.returncode, d["check"]["verdict"]), (style, d2["verdict"])


# ---------------------------------------------------------------------------------- composite, repair, note, paint

def test_composite_grades_all_of_a_layer_and_blurs_before_the_frame(tmp_path):
    """A layer's grade reaches all of it: a veil at a quarter or just under half alpha is greyed by chroma 0 as the solid
    one is (below half alpha it once kept its colour). A light just past the frame's edge, blurred, spreads into it
    (the frame was once cut before the blur, and the light lost)."""
    cv2.imwrite(str(tmp_path / "bg.png"), np.full((200, 300, 3), 128, np.uint8))
    sc_path = tmp_path / "scene.json"
    for a8 in (64, 127, 255):
        lay = np.zeros((100, 100, 4), np.uint8)
        lay[..., 2], lay[..., 3] = 255, a8
        cv2.imwrite(str(tmp_path / f"red{a8}.png"), lay)
        sc = {"frame": [300, 200], "background": {"image": "bg.png"},
              "layers": [{"image": f"red{a8}.png", "place": [50, 150, 1.0], "grade": {"chroma": 0}}]}
        sc_path.write_text(json.dumps(sc), encoding="utf-8")
        r, _ = run("composite.py", sc_path, tmp_path / "o.png")
        assert r.returncode == 0, r.stderr[-300:]
        px = cv2.imread(str(tmp_path / "o.png"))[100, 100].astype(int)
        assert px.max() - px.min() <= 3, (a8, px.tolist())
    cv2.imwrite(str(tmp_path / "black.png"), np.zeros((200, 300, 3), np.uint8))
    cv2.imwrite(str(tmp_path / "lamp.png"), np.full((120, 60, 4), 255, np.uint8))
    sc = {"frame": [300, 200], "background": {"image": "black.png"},
          "layers": [{"image": "lamp.png", "place": [304, 160, 1.0], "blur": 20}]}       # wholly past the right edge
    sc_path.write_text(json.dumps(sc), encoding="utf-8")
    r, _ = run("composite.py", sc_path, tmp_path / "o.png")
    assert r.returncode == 0 and cv2.imread(str(tmp_path / "o.png"))[100, 299].min() > 40
    # and a lamp in the background just past a zoom's window: the zoom once cut it off before the blur
    bg = np.zeros((200, 400, 3), np.uint8)
    bg[80:120, 205:245] = 255
    cv2.imwrite(str(tmp_path / "lamp_bg.png"), bg)
    sc = {"frame": [200, 100], "background": {"image": "lamp_bg.png", "zoom": 2.0, "centre": [0.25, 0.5], "blur": 20}}
    sc_path.write_text(json.dumps(sc), encoding="utf-8")
    r, _ = run("composite.py", sc_path, tmp_path / "o.png")
    assert r.returncode == 0 and cv2.imread(str(tmp_path / "o.png"))[50, 199].min() > 40


def test_line_repair_keeps_out_of_protected_boxes():
    """A gap in a line inside a protected box is left (the features are kept as drawn); the same gap outside is
    closed. repair.py passes the subject's boxes on."""
    from _core import Units
    from repair import fix_lines
    img = np.ones((300, 300, 3), np.float32)
    alpha = np.ones((300, 300), np.float32)
    for y in (100, 200):
        cv2.line(img, (40, y), (140, y), (0.15, 0.12, 0.14), 4)
        cv2.line(img, (148, y), (260, y), (0.15, 0.12, 0.14), 4)
    line = img.mean(-1) < 0.5
    U = Units(alpha, head_px=900)
    _, rep = fix_lines(img, alpha, U, line)
    assert rep["found"] == 2
    box = np.zeros((300, 300), bool)
    box[80:120, 120:170] = True
    out, rep = fix_lines(img, alpha, U, line, protect=box)
    assert rep["found"] == 1 and not (np.abs(out - img).max(-1) > 0.03)[box].any()
    assert (np.abs(out - img).max(-1) > 0.03)[190:210, 135:155].any()
    assert "protect=protect" in (SCRIPTS / "repair.py").read_text(encoding="utf-8")


def test_dark_dots_kept_on_a_face_not_known(draft, figure, tmp_path):
    """A dark dot is taken as a speck only off a known face: with the subject's focal face, a dot on the jacket goes and
    a mole on the cheek stays; with no focal face, both stay (the cheek's mole was once taken as a speck)."""
    im = cv2.imread(str(figure), cv2.IMREAD_UNCHANGED)
    spots = {"cheek": (205, 222), "jacket": (300, 470)}
    for x, y in spots.values():
        im[y:y + 3, x:x + 3, :3] = (40, 32, 36)
    p = tmp_path / "dots.png"
    cv2.imwrite(str(p), im)
    sj = json.loads(draft.read_text(encoding="utf-8"))
    assert any(f["name"] == "face" for f in sj["focal"])
    sj.pop("focal")
    nofocal = draft.with_name("nofocal.json")
    nofocal.write_text(json.dumps(sj), encoding="utf-8")

    def changed(subject):
        r, _ = run("repair.py", p, tmp_path / "out.png", "--fix", "specks", "--subject", subject)
        assert r.returncode == 0, r.stderr[-300:]
        out = cv2.imread(str(tmp_path / "out.png"), cv2.IMREAD_UNCHANGED)
        return {k: bool((np.abs(out[y:y + 3, x:x + 3, :3].astype(int) - im[y:y + 3, x:x + 3, :3].astype(int)) > 8).any())
                for k, (x, y) in spots.items()}

    assert changed(draft) == {"cheek": False, "jacket": True}
    assert changed(nofocal) == {"cheek": False, "jacket": False}
    # a face given little detail weight (strength 0.2) is a face all the same: its mole was once taken
    sj["focal"] = [dict(f, strength=0.2) for f in json.loads(draft.read_text(encoding="utf-8"))["focal"]]
    weak = draft.with_name("weakface.json")
    weak.write_text(json.dumps(sj), encoding="utf-8")
    assert changed(weak) == {"cheek": False, "jacket": True}


def test_png_note_replaces_a_compressed_note(tmp_path):
    """A note of the same key in a zTXt chunk (compressed) is replaced too, so no reader finds the old one; a note of
    another key and the pixels are kept."""
    import struct
    import zlib

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)

    p = tmp_path / "a.png"
    img = (np.random.default_rng(1).random((20, 30, 4)) * 255).astype(np.uint8)
    cv2.imwrite(str(p), img)
    data = p.read_bytes()
    i = 8 + 12 + struct.unpack(">I", data[8:12])[0]
    old = chunk(b"zTXt", b"Comment\x00\x00" + zlib.compress(b"OLD: hand drawn"))
    other = chunk(b"zTXt", b"Author\x00\x00" + zlib.compress(b"someone"))
    p.write_bytes(data[:i] + old + other + data[i:])
    _, d = run("png_note.py", p, "--read")
    assert d["notes"] == {"Comment": "OLD: hand drawn", "Author": "someone"}
    r, _ = run("png_note.py", p, "AI-assisted: refinished with tv-cel")
    assert r.returncode == 0
    data, notes, j = p.read_bytes(), [], 8
    while j < len(data):
        n = struct.unpack(">I", data[j:j + 4])[0]
        if data[j + 4:j + 8] in (b"tEXt", b"zTXt", b"iTXt"):
            notes.append(data[j + 8:j + 8 + n].split(b"\x00", 1)[0])
        j += 12 + n
    assert sorted(notes) == [b"Author", b"Comment"]
    _, d = run("png_note.py", p, "--read")
    assert d["notes"] == {"Comment": "AI-assisted: refinished with tv-cel", "Author": "someone"}
    assert np.array_equal(cv2.imread(str(p), cv2.IMREAD_UNCHANGED), img)


def test_paint_follows_its_own_seed(draft):
    """A paint finish with a given seed comes out the same whatever ran before it in the process (another finish in a
    recipe): its palette's k-means once drew from OpenCV's shared generator."""
    from _core import Units
    from _style import load_style, load_subject, resolve_style
    from parts import load_or_build
    import _paint
    sj = load_subject(draft)
    img, alpha, parts = load_or_build(sj)
    U = Units(alpha, sj.get("head_px"))
    st = load_style(resolve_style("gouache"))
    outs = []
    for g in (1, 987654):
        cv2.setRNGSeed(g)
        outs.append(_paint.run(sj, st, img, alpha, parts, U, seed=7)[0])
    assert np.array_equal(outs[0], outs[1])


# -------------------------------------------------------------------------------------------- paper cut, fit, tweak

def test_paper_cut_keeps_the_white_of_an_eye():
    """An eye's white a few points from a light skin, in a part of kind eyes inside a protected box, stays white under
    the paper cut: the eyes once lost their own sheet and the paste missed a white too close to the skin."""
    import _papercut
    from _core import Units
    from _style import load_style, resolve_style
    h, w = 320, 320
    yy, xx = np.mgrid[0:h, 0:w]
    face = (xx - 160) ** 2 + (yy - 170) ** 2 < 120 ** 2
    parts = np.zeros((h, w), np.uint8)
    parts[face] = 1
    cel = np.zeros((h, w, 3), np.float32)
    cel[face] = (0.99, 0.91, 0.85)                                   # a light skin
    eye = ((xx - 120) / 22.0) ** 2 + ((yy - 170) / 13.0) ** 2 < 1
    iris = (xx - 124) ** 2 + (yy - 170) ** 2 < 8 ** 2
    parts[eye], parts[iris] = 2, 3
    cel[eye], cel[iris] = (0.98, 0.98, 0.98), (0.25, 0.30, 0.45)
    alpha = face.astype(np.float32)
    sj = {"parts": [{"name": "skin", "kind": "skin"}, {"name": "eye-whites", "kind": "eyes"},
                    {"name": "irises", "kind": "eyes"}],
          "protect": [{"name": "eye", "box": [92, 150, 148, 190]}], "upscaled": 1}
    out, _ = _papercut.run(sj, load_style(resolve_style("paper-cut")), cel, alpha, parts, Units(alpha, 260))
    white = cv2.erode((eye & ~iris).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    assert np.abs(out[white] - 0.98).max(axis=1).mean() < 0.04, out[white].mean(0)

def test_paper_cut_closes_gaps_and_lays_the_eyes_on_the_face():
    """The paper cut's outer edge closes a narrow gap with the paper beside it (it once showed the colour hidden under
    the gap, black); an eye lies on the face's paper with no sheet of its own (whose shadow once made a dark ring
    under it); a strand of hair beside the eye in its box is paper like the rest (it was once pasted as drawn)."""
    import _papercut
    from _core import Units
    from _style import load_style, resolve_style
    h, w = 320, 320
    yy, xx = np.mgrid[0:h, 0:w]
    disc = (xx - 160) ** 2 + (yy - 170) ** 2 < 120 ** 2
    parts = np.zeros((h, w), np.uint8)
    parts[disc] = 1                                                  # skin
    parts[disc & (yy < 110)] = 2                                     # hair
    slit = (np.abs(xx - 160) <= 1) & (yy < 70)                       # a gap 3 px wide into the hair
    alpha = (disc & ~slit).astype(np.float32)
    parts[slit] = 0
    cel = np.zeros((h, w, 3), np.float32)                            # (black under the gap, as a file's hidden colour)
    cel[parts == 1] = (0.98, 0.86, 0.78)
    cel[parts == 2] = (0.36, 0.26, 0.22)
    eye = ((xx - 120) / 16.0) ** 2 + ((yy - 170) / 10.0) ** 2 < 1
    parts[eye] = 3
    cel[eye] = (0.97, 0.97, 0.98)
    cel[(xx - 120) ** 2 + (yy - 170) ** 2 < 49] = (0.30, 0.20, 0.12)
    strand = (np.abs(xx - 99) <= 1) & (yy >= 152) & (yy <= 190)
    parts[strand] = 2
    cel[strand] = (0.36, 0.26, 0.22)
    sj = {"parts": [{"name": "skin", "kind": "skin"}, {"name": "hair", "kind": "hair"}, {"name": "eyes", "kind": "eyes"}],
          "protect": [{"name": "eye", "box": [96, 150, 144, 192]}], "upscaled": 1}
    out, info = _papercut.run(sj, load_style(resolve_style("paper-cut")), cel, alpha, parts, Units(alpha, 260))
    closed = slit & (info["alpha"] > 0.5)
    assert closed.sum() > 30 and np.abs(out[closed].mean(0) - cel[parts == 2][0]).max() < 0.05
    under = (np.abs(xx - 124) <= 10) & (yy >= 182) & (yy <= 188)
    away = (np.abs(xx - 200) <= 10) & (yy >= 182) & (yy <= 188)
    assert abs(float(out[under].mean()) - float(out[away].mean())) < 0.02
    assert np.abs(out[strand & (yy > 160) & (yy < 185)].mean(0) - cel[parts == 1][0]).max() < 0.05


def test_fit_style_starts_from_a_cel_style(draft, figure, tmp_path):
    """fit_style.py moves the cel finishes' settings only, so a start in another technique is refused with exit 2."""
    r, _ = run("fit_style.py", draft, figure, "--out", tmp_path / "fit.json", "--start", "watercolour")
    assert r.returncode == 2 and "cel" in r.stderr and "Traceback" not in r.stderr


def test_tweak_reports_every_step(tmp_path):
    """--steps N reports each key from before the first step to after the last (a number the style does not set from
    the engine's default), as written to the file."""
    from _adjectives import DEFAULTS
    out = tmp_path / "t.json"
    r, d = run("tweak_style.py", "tv-cel", out, "softer shadows", "--steps", "3")
    assert r.returncode == 0 and d["changed"]
    st0 = json.loads((SKILL / "styles" / "tv-cel.json").read_text(encoding="utf-8"))
    st1 = json.loads(out.read_text(encoding="utf-8"))

    def get(s, path):
        for k in path.split("."):
            s = s.get(k) if isinstance(s, dict) else None
        return s

    for ch in d["changed"]:
        was = get(st0, ch["key"])
        assert ch["was"] == (DEFAULTS.get(ch["key"], 0.0) if was is None else was), ch
        assert ch["now"] == get(st1, ch["key"]), ch


# ----------------------------------------------------------------------------------- bad input and stale outputs

def test_more_bad_input_stops_with_a_message(draft, figure, tmp_path):
    """A crop box that holds nothing, a grid step of 0, a de-AI finish without a region map and a part map's cache
    whose region map is gone all end with exit 2 and a message; a sliver of skin colour is no face to read; the review
    lists only the files this run wrote."""
    import shutil
    from pathlib import Path
    r, _ = run("prep.py", figure, tmp_path / "p.png", "--box", "300,300,100,100")
    assert r.returncode == 2 and "Traceback" not in r.stderr
    r, _ = run("zoom.py", figure, "100,100,300,300", tmp_path / "z.jpg", "--step", "0")
    assert r.returncode == 2 and "Traceback" not in r.stderr
    sj = json.loads(draft.read_text(encoding="utf-8"))
    sj["image"] = str(figure.resolve()).replace("\\", "/")
    noreg = tmp_path / "noreg.json"
    noreg.write_text(json.dumps({k: v for k, v in sj.items() if k != "regions"}), encoding="utf-8")
    r, _ = run("refinish.py", noreg, "deai-light", tmp_path / "d.png", "--no-check")
    assert r.returncode == 2 and "Traceback" not in r.stderr and "region map" in r.stderr
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "subject.json").write_text(json.dumps(sj), encoding="utf-8")
    shutil.copy(draft.with_name(sj["regions"]), cache / sj["regions"])
    r, _ = run("refinish.py", cache / "subject.json", "tv-cel", tmp_path / "a.png", "--no-check")
    assert r.returncode == 0, r.stderr[-300:]
    (cache / sj["regions"]).unlink()
    r, _ = run("refinish.py", cache / "subject.json", "tv-cel", tmp_path / "b.png", "--no-check")
    assert r.returncode == 2 and "Traceback" not in r.stderr

    from auto_parts import eyes_in
    F = np.zeros((80, 40), bool)
    F[10:70, 18:21] = True
    eyes, sure, _, _ = eyes_in(F, F.copy(), np.full(F.shape, 85.0, np.float32), np.ones(F.shape, bool),
                               np.ones(F.shape, np.int32), np.zeros(F.shape, bool))
    assert eyes == [] and sure == 0.0

    im = np.zeros((600, 300, 4), np.uint8)
    cv2.ellipse(im, (150, 300), (100, 240), 0, 0, 360, (160, 90, 40, 255), -1)
    cv2.ellipse(im, (150, 300), (100, 240), 0, 0, 360, (40, 32, 36, 255), 2)
    cv2.imwrite(str(tmp_path / "noface.png"), im)
    (tmp_path / "noface_sub.face.jpg").write_bytes(b"an earlier draft's face sheet")
    r, d = run("auto_parts.py", tmp_path / "noface.png", tmp_path / "noface_sub.json")
    assert r.returncode in (0, 1) and d["review"] and all(Path(f).is_file() for f in d["review"])
    assert not (tmp_path / "noface_sub.face.jpg").exists()


# ----------------------------------------------------------------------------------------------------------- recolour

# CIEDE2000's test pairs (CIELAB 1, CIELAB 2, the difference): Sharma, Wu and Dalal, "The CIEDE2000 color-difference
# formula: implementation notes, supplementary test data, and mathematical observations", Color Research &
# Application 30(1), 2005, table 1
SHARMA = """
50.0000 2.6772 -79.7751 50.0000 0.0000 -82.7485 2.0425
50.0000 3.1571 -77.2803 50.0000 0.0000 -82.7485 2.8615
50.0000 2.8361 -74.0200 50.0000 0.0000 -82.7485 3.4412
50.0000 -1.3802 -84.2814 50.0000 0.0000 -82.7485 1.0000
50.0000 -1.1848 -84.8006 50.0000 0.0000 -82.7485 1.0000
50.0000 -0.9009 -85.5211 50.0000 0.0000 -82.7485 1.0000
50.0000 0.0000 0.0000 50.0000 -1.0000 2.0000 2.3669
50.0000 -1.0000 2.0000 50.0000 0.0000 0.0000 2.3669
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0009 7.1792
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0010 7.1792
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0011 7.2195
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0012 7.2195
50.0000 -0.0010 2.4900 50.0000 0.0009 -2.4900 4.8045
50.0000 -0.0010 2.4900 50.0000 0.0010 -2.4900 4.8045
50.0000 -0.0010 2.4900 50.0000 0.0011 -2.4900 4.7461
50.0000 2.5000 0.0000 50.0000 0.0000 -2.5000 4.3065
50.0000 2.5000 0.0000 73.0000 25.0000 -18.0000 27.1492
50.0000 2.5000 0.0000 61.0000 -5.0000 29.0000 22.8977
50.0000 2.5000 0.0000 56.0000 -27.0000 -3.0000 31.9030
50.0000 2.5000 0.0000 58.0000 24.0000 15.0000 19.4535
50.0000 2.5000 0.0000 50.0000 3.1736 0.5854 1.0000
50.0000 2.5000 0.0000 50.0000 3.2972 0.0000 1.0000
50.0000 2.5000 0.0000 50.0000 1.8634 0.5757 1.0000
50.0000 2.5000 0.0000 50.0000 3.2592 0.3350 1.0000
60.2574 -34.0099 36.2677 60.4626 -34.1751 39.4387 1.2644
63.0109 -31.0961 -5.8663 62.8187 -29.7946 -4.0864 1.2630
61.2901 3.7196 -5.3901 61.4292 2.2480 -4.9620 1.8731
35.0831 -44.1164 3.7933 35.0232 -40.0716 1.5901 1.8645
22.7233 20.0904 -46.6940 23.0331 14.9730 -42.5619 2.0373
36.4612 47.8580 18.3852 36.2715 50.5065 21.2231 1.4146
90.8027 -2.0831 1.4410 91.1528 -1.6435 0.0447 1.4441
90.9257 -0.5406 -0.9208 88.6381 -0.8985 -0.7239 1.5381
6.7747 -0.2908 -2.4247 5.8714 -0.0985 -2.2286 0.6377
2.0776 0.0795 -1.1350 0.9033 -0.0636 -0.5514 0.9082
"""


def test_ciede2000_matches_the_published_pairs():
    import _colour as C
    t = np.array([[float(v) for v in ln.split()] for ln in SHARMA.strip().splitlines()])
    assert t.shape == (34, 7)
    got = C.ciede2000(t[:, :3], t[:, 3:6])
    assert np.abs(got - t[:, 6]).max() < 1e-3
    assert np.allclose(C.ciede2000(t[:, 3:6], t[:, :3]), got)


def test_oklab_reference_values():
    """sRGB's white and primaries in Oklab, as CSS Color 4 gives them, and back."""
    import _colour as C
    rgb = np.array([[1, 1, 1], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    ref = np.array([[1.0, 0.0, 0.0], [0.62796, 0.22486, 0.12585], [0.86644, -0.23389, 0.1795],
                    [0.45201, -0.03246, -0.31153]])
    ok = C.srgb_to_oklab(rgb)
    assert np.abs(ok - ref).max() < 2e-4
    assert np.abs(C.oklab_to_srgb(ok) - rgb).max() < 1e-4


def test_gamut_map_keeps_lightness_and_hue():
    """A colour sRGB cannot show is brought in by chroma alone (CSS Color 4): the result shows, has less chroma, and
    lies within a just noticeable difference of the colour of the same lightness and hue at that chroma."""
    import _colour as C
    lch = np.array([[0.7, 0.35, h] for h in range(0, 360, 30)] + [[0.3, 0.3, 140.0], [0.95, 0.2, 260.0]])
    rgb = C.oklab_to_srgb(C.from_lch(lch))
    assert rgb.min() >= 0 and rgb.max() <= 1
    back = C.to_lch(C.srgb_to_oklab(rgb))
    assert (back[:, 1] < lch[:, 1]).all()
    on_hue = C.from_lch(np.stack([lch[:, 0], back[:, 1], lch[:, 2]], -1))
    assert C.delta_eok(C.srgb_to_oklab(rgb), on_hue).max() <= C.JND + 1e-3
    inside = np.array([[0.5, 0.05, 40.0]])                         # a colour sRGB shows is left as it is
    assert np.abs(C.to_lch(C.srgb_to_oklab(C.oklab_to_srgb(C.from_lch(inside)))) - inside).max() < 1e-4


def test_derived_shadows_turn_cool_skin_warm_whites_tinted():
    """A base's shadow is a step darker and richer with its hue turned toward blue-violet (at most 18 degrees), skin's
    toward red (at most 10), a near-white's given a cool tint; the second shadow lies below it, the light above."""
    import _colour as C
    import _palette as P

    def lch(rgb):
        return C.to_lch(C.srgb_to_oklab(np.asarray(rgb, float)))

    def turn(a, b):
        return (b - a + 180) % 360 - 180

    for hexc, kind, toward, cap in (("#d08040", "cloth", 290.0, 18.0), ("#3a6fd0", "cloth", 290.0, 18.0),
                                    ("#f0c8a8", "skin", 30.0, 10.0)):
        base = C.parse_hex(hexc)
        d = P.derive(base, kind)
        b, s, dp, hl = lch(base), lch(d["shadow"]), lch(d["deep"]), lch(d["highlight"])
        assert dp[0] < s[0] < b[0] < hl[0], hexc
        assert s[1] > b[1], hexc
        t = turn(b[2], s[2])
        assert 0 < abs(t) <= cap + 0.5 and abs(turn(s[2], toward)) < abs(turn(b[2], toward)), hexc
    white = lch(P.derive(C.parse_hex("#f4f4f4"), "cloth-white")["shadow"])
    assert abs(white[1] - P.RULE["neutral_tint"]) < 0.005 and abs(turn(white[2], 290.0)) < 2


def card_file(tmp_path, card, name="card.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"format": "refinish-palette/1", **card}), encoding="utf-8")
    return p


def test_card_entries_match_by_name_then_iris_kind_and_role(tmp_path):
    """A part named on the card wins; then an iris; then the part's kind; the roles go to the clothes by area (the
    largest the main colour, the next the sub colour, the rest the accent), never to a feature of the face or to
    solid black ink; a hair clip is no lip."""
    import _palette as P
    parts = (("hair", "hair", 9000, (40, 10, 10)), ("coat", "cloth", 20000, (50, 5, -20)),
             ("scarf", "cloth", 6000, (60, 30, 20)), ("clip", "accessory", 300, (70, 0, 40)),
             ("lips", "accessory", 200, (45, 30, 10)), ("ink", "accessory", 4000, (3, 0, 0)),
             ("iris", "eyes", 400, (35, 5, 20)), ("eye-white", "eyes", 300, (95, 0, -2)),
             ("skin", "skin", 15000, (85, 12, 18)), ("boots", "gloss", 3000, (20, 2, 2)))
    sj = {"parts": [{"name": n, "kind": k} for n, k, _, _ in parts]}
    stats = {n: {"area": a, "kind": k, "lab": np.array(c, float), "in_boxes": 1.0 if n == "lips" else 0.0}
             for n, k, a, c in parts}
    card = P.load_palette(card_file(tmp_path, {"parts": {"Boots": "#202040"}, "kinds": {"hair": "#e0b040"},
                                               "iris": "#d04040",
                                               "roles": {"main": "#2e7d5b", "sub": "#c03050", "accent": "#f0d040"}}))
    got = {n: w for n, (_, w) in P.match(sj, card, stats).items()}
    assert got == {"boots": "parts", "iris": "iris", "hair": "kinds", "coat": "roles.main", "scarf": "roles.sub",
                   "clip": "roles.accent"}


def test_a_prop_keeps_its_colours_unless_the_card_names_it(tmp_path):
    """A thing the character holds (a painter's brush, a cup) is no part of the costume: the kinds and the roles pass
    it by, and only a card that names it recolours it."""
    import _palette as P
    parts = (("coat", "cloth", 20000, (50, 5, -20)), ("brush", "cloth", 9000, (40, 10, 30)),
             ("sword", "metal", 3000, (70, 0, 0)), ("cup", "cloth", 2000, (80, 5, 5)))
    sj = {"parts": [{"name": n, "kind": k, **({} if n == "coat" else {"prop": True})} for n, k, _, _ in parts]}
    stats = {n: {"area": a, "kind": k, "lab": np.array(c, float), "in_boxes": 0.0} for n, k, a, c in parts}
    card = P.load_palette(card_file(tmp_path, {"parts": {"cup": "#f0d040"}, "kinds": {"metal": "#c0c0d0"},
                                               "roles": {"main": "#2e7d5b", "sub": "#c03050"}}))
    got = {n: w for n, (_, w) in P.match(sj, card, stats).items()}
    assert got == {"coat": "roles.main", "cup": "parts"}


def test_card_mistakes_stop_with_a_message(tmp_path):
    for card in ({"parts": {"hair": "c8442"}}, {"roles": {"primary": "#c8442f"}}, {"grade": "loud"}, {"parts": []},
                 {"kinds": {"clothes": "#c8442f"}}, {"shadow_rule": {"darkness": 0.2}}):
        p = card_file(tmp_path, card)
        r, _ = run("palette.py", "board", p, tmp_path / "b.png")
        assert r.returncode == 2 and "Traceback" not in r.stderr, card
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"parts": {"hair": "#c8442f"}}), encoding="utf-8")
    r, _ = run("palette.py", "board", p, tmp_path / "b.png")
    assert r.returncode == 2 and "refinish-palette/1" in r.stderr


def test_palette_derive_board_and_read(tmp_path):
    r, d = run("palette.py", "derive", "#c8442f", "--kind", "skin")
    assert r.returncode == 0 and all(re.fullmatch(r"#[0-9a-f]{6}", d[k]) for k in ("shadow", "deep", "highlight"))
    card = card_file(tmp_path, {"parts": {"hair": "#c8442f", "coat": {"base": "#2e7d5b", "shadow": "#1d5a40"}},
                                "iris": "#3a8fd0"})
    r, d = run("palette.py", "board", card, tmp_path / "board.png")
    assert r.returncode == 0 and d["rows"] == 3 and (tmp_path / "board.png").is_file()
    # a picture of flat swatches read back: their colours, each once
    im = np.full((220, 640, 3), 255, np.uint8)
    cols = ((200, 68, 47), (46, 125, 91), (240, 200, 60))
    for i, c in enumerate(cols):
        cv2.rectangle(im, (20 + i * 210, 40), (200 + i * 210, 180), c[::-1], -1)
    cv2.imwrite(str(tmp_path / "swatches.png"), im)
    r, d = run("palette.py", "read", tmp_path / "swatches.png")
    assert r.returncode == 0
    assert sorted(s["hex"] for s in d["swatches"] if s["hex"] != "#ffffff") == sorted(
        "#%02x%02x%02x" % c for c in cols)


def test_transfer_keeps_the_order_of_tones_and_lands_on_the_knots():
    """A part's own tones carried onto the card: lighter stays lighter, its usual lit tone lands on the base, the
    darkest stays darker than the second shadow, and an eye's catchlight stays white."""
    import _colour as C
    import _palette as P
    import _recolour as rc
    rng = np.random.default_rng(3)
    grey = np.sort(rng.uniform(0.12, 0.85, 3999))
    img = np.concatenate([np.repeat(grey[:, None], 3, 1), [[1.0, 1.0, 1.0]]]).reshape(40, 100, 3).astype(np.float32)
    mask = np.ones((40, 100), bool)
    base = C.parse_hex("#3a8fd0")
    rec = {"base": C.to_hex(base), **{k: C.to_hex(v) for k, v in P.derive(base, "eyes").items()}}
    out = rc.transfer(img, mask, rc.knots(rec), keep=0.0, white_keep=True)
    Ls, Lo = C.srgb_to_oklab(img[mask])[:, 0], C.srgb_to_oklab(out)[:, 0]
    order = np.argsort(Ls[:-1], kind="stable")
    assert (np.diff(Lo[:-1][order]) > -2e-3).all()
    kL = {k: C.srgb_to_oklab(C.parse_hex(rec[k]))[0] for k in ("deep", "base")}
    assert abs(np.percentile(Lo[:-1], 62) - kL["base"]) < 0.02
    assert Lo[:-1].min() < kL["deep"]
    assert np.allclose(out[-1], 1.0)


def test_only_the_iris_of_an_eye_part_takes_the_iris_colour():
    """An eye part drawn wide over the white of the eye and the skin: only its iris-like pixels are the iris's (a pale
    blue iris as light as the skin is still one; a grey white of the eye and the skin's own colour are not)."""
    import _recolour as rc
    skin = np.array([80.0, 12.0, 18.0])
    px = np.array([[[35.0, 10.0, 25.0],      # a brown iris
                    [78.0, -8.0, -20.0],     # a pale blue iris, as light as the skin
                    [79.0, 11.0, 17.0],      # the skin
                    [82.0, -1.0, -3.0],      # the white of the eye, grey-blue
                    [97.0, 0.0, 0.0]]])      # a catchlight
    assert rc.iris_like(px, skin).tolist() == [[True, True, False, False, False]]
    assert rc.iris_like(px, None).all()


def test_the_iris_is_the_eye_parts_thick_mass():
    """A dark iris part the part map joined to the upper lash line, a lash's tail and a strand of hair running out of
    the eye's box: the iris keeps its whole disc, its catchlight a hole in it; the lash line, the thin strips and what
    lies beyond the box are not the iris. With no eye box, the part as it is. (A lash line that closes a gap with the
    iris and another strip is held as the iris's: the gap is filled as a catchlight would be.)"""
    import _recolour as rc
    h, w = 200, 200
    yy, xx = np.mgrid[:h, :w]
    disc = (yy - 100) ** 2 + (xx - 100) ** 2 <= 30 ** 2          # the iris
    light = (yy - 92) ** 2 + (xx - 108) ** 2 <= 10 ** 2           # its catchlight, not iris-like
    m = disc & ~light
    m[50:72, 60:140] = True                                       # the upper lash line, over the iris's top
    m[78:100, 128:132] = True                                     # a lash's tail, off the iris's side
    m[0:75, 50:53] = True                                         # a strand from above, out of the box
    subject = {"protect": [{"name": "left eye", "box": [55, 60, 145, 140]}]}
    core = rc.iris_core(subject, m)
    assert core[disc & ~light].mean() > 0.99 and not core[light].any()
    assert not core[50:64, 60:140].any()
    assert not core[78:85, 128:132].any() and not core[0:75, 50:53].any()
    assert (rc.iris_core({}, m) == m).all()


def test_the_part_map_is_mended_for_a_card():
    """A small piece of the recoloured hair far from it, inside a book (gold ornaments read as blonde hair), is kept as
    drawn, unless the card paints it; the hair an iris part took round the eye goes back to the hair."""
    import _recolour as rc
    from _core import Units
    h, w = 400, 300
    img = np.full((h, w, 3), 0.92, np.float32)
    alpha = np.zeros((h, w), np.float32)
    alpha[20:390, 20:280] = 1
    parts = np.zeros((h, w), np.uint8)
    parts[20:390, 20:280] = 3                                     # 3: the coat
    parts[20:140, 20:280] = 1                                     # 1: the hair, the top of the figure
    img[parts == 1] = (0.85, 0.7, 0.3)
    img[parts == 3] = (0.2, 0.25, 0.5)
    parts[250:330, 60:200] = 2                                    # 2: a book on the coat
    img[250:330, 60:200] = (0.1, 0.15, 0.35)
    parts[280:296, 120:136] = 1                                   # a gold ornament, read as hair
    img[280:296, 120:136] = (0.85, 0.7, 0.3)
    parts[100:120, 130:170] = 4                                   # 4: an iris part that took the hair over the eye
    parts[110:118, 140:160] = 4
    img[100:110, 130:170] = (0.85, 0.7, 0.3)                      # (the hair's colour, joined to the hair above)
    img[110:118, 140:160] = (0.2, 0.4, 0.8)                       # (the iris itself, blue)
    img[109, 130:170] = 0.05                                      # (the lash line between them)
    subject = {"parts": [{"name": "hair", "kind": "hair"}, {"name": "book", "kind": "cloth-dark"},
                         {"name": "coat", "kind": "cloth"}, {"name": "iris", "kind": "eyes"}],
               "protect": [{"name": "left eye", "box": [120, 95, 180, 125]}],
               "recolour": {"parts": {"hair": {"base": "#c8442f"}, "iris": {"base": "#30a060"}}}}
    kinds = [None, "hair", "cloth-dark", "cloth", "eyes"]
    U = Units(alpha)
    mended, kept, pieces = rc.mend_parts(subject, img, alpha, parts, U, kinds)
    assert kept[285, 125] and not kept[60, 60] and [p[:2] for p in pieces] == [("hair", "book")]
    assert mended[102, 150] == 1 and mended[114, 150] == 4
    subject["recolour"]["parts"]["hair"]["pieces"] = "paint"
    assert not rc.mend_parts(subject, img, alpha, parts, U, kinds)[1].any()


def test_a_touch_reaches_the_fill_round_its_point():
    """A touch's point reaches the colour round it, as far as that colour goes without crossing a line: within its tol,
    inside its box; a point on a line reaches the line itself, inside its box or close round the point."""
    import _recolour as rc
    from _core import Units
    h, w = 200, 300
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.8, 0.3, 0.3)                                      # red
    img[100:, :100] = (0.74, 0.3, 0.3)                            # a slightly darker red, the lower left
    img[:, 150:] = (0.3, 0.3, 0.8)                                # blue
    img[:, 100:103] = 0.02                                        # a line through the red
    line = np.zeros((h, w), bool)
    line[:, 100:103] = True
    alpha = np.ones((h, w), np.float32)
    touches = [{"at": [[50, 50]], "as": "x"}, {"at": [[120, 50]], "as": "x"}, {"at": [[50, 50]], "as": "x", "tol": 2},
               {"at": [[50, 50]], "as": "x", "box": [0, 0, 80, 200]}, {"at": [[101, 50]], "keep": True,
                                                                       "box": [90, 40, 120, 60]},
               {"at": [[101, 150]], "keep": True}, {"at": [[500, 50]], "keep": True}]
    m = [m_ for m_, _ in rc.touch_masks({"recolour": {"touch": touches}}, img, alpha, Units(alpha), line=line)]
    assert m[0][:, :100].all() and not m[0][:, 100:].any()        # the red left of the line, both reds
    assert m[1][:, 103:150].all() and not m[1][:, :103].any() and not m[1][:, 150:].any()
    assert m[2][:100, :100].all() and not m[2][100:].any()        # a tight tol: one red
    assert m[3][:, :80].all() and not m[3][:, 80:].any()          # its box
    assert m[4][40:60, 100:103].all() and m[4].sum() == 60        # on the line: the line, in the box
    assert m[5].any() and not m[5][:140].any() and not m[5][161:].any()
    assert not m[6].any()                                         # off the picture: nothing


def test_touches_mend_the_part_map_last():
    """The touches are the agent's word over the part map: a patch given to another part goes to it, a patch kept is
    kept as drawn, a patch given a colour of its own is left out of every part."""
    import _recolour as rc
    from _core import Units
    h, w = 120, 120
    img = np.full((h, w, 3), 0.55, np.float32)
    alpha = np.ones((h, w), np.float32)
    parts = np.ones((h, w), np.uint8)                             # 1: coat
    parts[:, 60:] = 2                                             # 2: skirt
    img[:, 60:] = (0.25, 0.3, 0.6)
    img[20:40, 20:40] = (0.8, 0.7, 0.2)                           # a patch in the coat, given to the skirt
    img[70:90, 70:90] = (0.9, 0.9, 0.9)                           # a patch in the skirt, kept as drawn
    img[90:110, 20:40] = (0.2, 0.6, 0.2)                          # a patch in the coat, a colour of its own
    to = {"base": "#2050c0", "shadow": "#183c90", "deep": "#102a70", "highlight": "#8aa8ff"}
    subject = {"parts": [{"name": "coat", "kind": "cloth"}, {"name": "skirt", "kind": "cloth"}],
               "recolour": {"parts": {"coat": {"base": "#c8442f"}},
                            "touch": [{"at": [[30, 30]], "as": "skirt"}, {"at": [[80, 80]], "keep": True},
                                      {"at": [[30, 100]], "to": to}]}}
    mended, kept, _ = rc.mend_parts(subject, img, alpha, parts, Units(alpha), [None, "cloth", "cloth"])
    assert (mended[20:40, 20:40] == 2).all() and not kept[20:40, 20:40].any()
    assert kept[70:90, 70:90].all() and kept[90:110, 20:40].all()
    assert (mended[0:15, 0:15] == 1).all() and not kept[0:15, 0:15].any()


def test_boxes_give_way_only_to_parts_reaching_in():
    """Inside an eye's protected box, the hair that reaches in from outside (bangs) takes the card's colours; a lash
    the part map gave to the hair (drawn darker than any of the hair's own tones) and a speck labelled hair only inside
    the box stay as drawn. An iris labelled hair is reported, and that eye is left as drawn."""
    import _recolour as rc
    h, w = 100, 100
    parts = np.full((h, w), 2, np.uint8)                          # 2: skin
    Lv = np.full((h, w), 85.0, np.float32)
    parts[0:40, 20:80] = 1                                        # 1: hair, the bangs into the box's top
    Lv[0:40, 20:80] = 35.0
    parts[40:44, 30:70] = 1                                       # a lash, labelled hair, touching the bangs
    Lv[40:44, 30:70] = 12.0
    parts[55:58, 60:63] = 1                                       # a speck labelled hair, alone in the box
    Lv[55:58, 60:63] = 35.0
    subject = {"protect": [{"name": "left eye", "box": [30, 30, 70, 70]}]}
    within = np.ones((h, w), bool)
    got = rc.reaching_in(subject, parts, [1], within, Lv)
    assert got[32:40, 35:65].all()
    assert not got[40:44].any() and not got[55:58, 60:63].any() and not got[:30].any()
    kinds = [None, "hair", "skin", "eyes"]
    lab_ = np.stack([Lv, np.where(parts == 2, 12.0, 4.0), np.where(parts == 2, 18.0, 4.0)], -1).astype(np.float32)
    parts[44:60, 40:60] = 3                                       # 3: the iris, under the lash
    lab_[44:60, 40:60] = (40.0, 10.0, 25.0)
    assert rc.mislabelled_irises(subject, lab_, within, parts, kinds, parts == 2) == []
    parts[44:60, 40:60] = 1                                       # the iris labelled hair
    assert rc.mislabelled_irises(subject, lab_, within, parts, kinds, parts == 2) == [[30, 30, 70, 70]]


@pytest.fixture(scope="module")
def hinted(figure, tmp_path_factory):
    """The figure enlarged and parted with the hints, as the workflow does; and its finish without a card."""
    d = tmp_path_factory.mktemp("hinted")
    image = d / "image.png"
    r, p = run("prep.py", figure, image, "--scale", "2")
    assert r.returncode == 0, r.stderr[-400:]
    x0, y0 = p["box"][:2]

    def at(x, y):
        return [(x - x0) * 2, (y - y0) * 2]

    hints = {"eyes": [at(*b[:2]) + at(*b[2:]) for b in HINTS["eyes"]],
             "mouth": at(*HINTS["mouth"][:2]) + at(*HINTS["mouth"][2:]),
             "parts": [{**q, "at": [at(*xy) for xy in q["at"]]} for q in HINTS["parts"]]}
    (d / "hints.json").write_text(json.dumps(hints), encoding="utf-8")
    r, _ = run("auto_parts.py", image, d / "subject.json", "--upscaled", "2", "--hints", d / "hints.json")
    assert r.returncode in (0, 1), r.stderr[-400:]
    r, _ = run("refinish.py", d / "subject.json", "tv-cel", d / "plain.png", "--no-check")
    assert r.returncode == 0, r.stderr[-400:]
    return d / "subject.json", d / "plain.png", at


def test_a_card_recolours_its_parts_and_their_lines(hinted, tmp_path):
    """The card's parts come out in its colours (no RC finding), the rest as the finish paints them without a card,
    the lines round the hair leaning to the new hair's hue (色トレス), the irises in the card's."""
    import _colour as C
    from _core import lab, load_rgba
    from _style import load_subject
    from parts import load_or_build
    subject, plain_png, at = hinted
    card = card_file(tmp_path, {"name": "test", "parts": {"jacket": "#2e7d5b"}, "kinds": {"hair": "#e0b040"},
                                "iris": "#d04040"})
    r, d = run("palette.py", "apply", subject, card, tmp_path / "carded.json")
    assert r.returncode == 0, r.stderr[-400:]
    assert d["recoloured"]["jacket"]["from"] == "parts" and d["recoloured"]["hair"]["from"] == "kinds"
    assert [n for n, v in d["recoloured"].items() if v["from"] == "iris"]
    assert {"trousers", "shoes", "skin"} <= set(d["kept_as_drawn"])
    out = tmp_path / "out.png"
    r, d = run("refinish.py", tmp_path / "carded.json", "tv-cel", out)
    assert r.returncode in (0, 1), r.stderr[-600:]
    assert not [f for f in d["check"]["findings"] if f.startswith("RC")], d["check"]["findings"]
    res, _ = load_rgba(out)
    plain, _ = load_rgba(plain_png)
    x, y = at(180, 700)                                            # the trousers: as without a card
    assert np.abs(res[y - 4:y + 5, x - 4:x + 5] - plain[y - 4:y + 5, x - 4:x + 5]).max() < 0.02
    sj = load_subject(tmp_path / "carded.json")
    _, alpha, parts = load_or_build(sj)
    names = [p["name"] for p in sj["parts"]]
    hair = parts == names.index("hair") + 1
    ring = cv2.dilate(hair.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~hair & (alpha > 0.5)
    f_new = lab(res)
    dark = ring & (f_new[..., 0] < 45)
    new_ab = C.srgb_to_oklab(C.parse_hex("#e0b040"))[1:]
    line_ab = C.srgb_to_oklab(res[dark]).mean(0)[1:]
    old_ab = C.srgb_to_oklab(plain[dark]).mean(0)[1:]
    assert dark.sum() > 50 and np.dot(line_ab, new_ab) > np.dot(old_ab, new_ab) + 1e-3
    iris = np.zeros(parts.shape, bool)
    for p in sj["protect"]:
        if "eye" in p["name"]:
            x0, y0, x1, y1 = p["box"]
            iris[y0:y1, x0:x1] = True
    iris &= np.hypot(f_new[..., 1], f_new[..., 2]) > 8
    h_card = np.degrees(np.arctan2(*C.srgb_to_oklab(C.parse_hex("#d04040"))[[2, 1]])) % 360
    h_iris = np.degrees(np.arctan2(*np.median(C.srgb_to_oklab(res[iris]), 0)[[2, 1]])) % 360
    assert iris.sum() > 50 and abs((h_iris - h_card + 180) % 360 - 180) < 25


def test_touches_after_a_look(hinted, tmp_path):
    """Touches written after looking at a result: a piece of the trousers given to the jacket takes the jacket's card
    colour, a shoe given a colour of its own takes it, a piece of the jacket kept stays as drawn. The report gives each
    touch's reach and the preview shows it; zoom draws a box of the result with its coordinates."""
    import _colour as C
    from _core import load_rgba
    subject, _, at = hinted
    card = card_file(tmp_path, {"parts": {"jacket": "#2e7d5b"}})
    touch = tmp_path / "touch.json"
    touch.write_text(json.dumps({"format": "refinish-touch/1", "touch": [
        {"at": at(310, 760), "as": "Jacket"}, {"at": at(175, 848), "to": "#c8442f"},
        {"at": [at(320, 450)], "keep": True}]}), encoding="utf-8")
    r, d = run("palette.py", "apply", subject, card, tmp_path / "carded.json", "--touch", touch)
    assert r.returncode == 0, r.stderr[-400:]
    assert [t["px"] > 0 for t in d["touches"]] == [True] * 3 and d["touches"][0]["as"] == "jacket"
    assert (tmp_path / "carded.touch.jpg").is_file()
    out = tmp_path / "out.png"
    r, _ = run("refinish.py", tmp_path / "carded.json", "tv-cel", out)
    assert r.returncode in (0, 1), r.stderr[-600:]
    res, _ = load_rgba(out)
    src, _ = load_rgba(subject.parent / "image.png")

    def hue(ok):
        return np.degrees(np.arctan2(ok[2], ok[1])) % 360

    def near(xy, hexc):
        x, y = xy
        got = np.median(C.srgb_to_oklab(res[y - 3:y + 4, x - 3:x + 4].reshape(-1, 3)), 0)
        return abs((hue(got) - hue(C.srgb_to_oklab(C.parse_hex(hexc))) + 180) % 360 - 180) < 30

    assert near(at(310, 760), "#2e7d5b") and near(at(175, 848), "#c8442f")
    x, y = at(320, 450)
    assert np.abs(res[y - 1:y + 2, x - 1:x + 2] - src[y - 1:y + 2, x - 1:x + 2]).max() < 0.02
    r, z = run("palette.py", "zoom", out, ",".join(str(v) for v in at(150, 400) + at(350, 500)),
               "--out", tmp_path / "zoom.jpg")
    assert r.returncode == 0 and (tmp_path / "zoom.jpg").is_file() and z["grid"] > 0


def test_touch_mistakes_stop_with_a_message(hinted, tmp_path):
    subject, _, _ = hinted
    card = card_file(tmp_path, {"parts": {"jacket": "#2e7d5b"}})
    p = tmp_path / "touch.json"
    for touch in ({"touch": [{"as": "jacket"}]}, {"touch": [{"at": [1, 2], "as": "jacket", "keep": True}]},
                  {"touch": [{"at": [1, 2], "as": "cape"}]}, {"touch": [{"at": [1, 2], "to": "red"}]},
                  {"touch": [{"at": [1, 2], "keep": True, "tol": 0}]},
                  {"touch": [{"at": [1, 2], "keep": True, "box": [5, 5, 1, 1]}]}, {"touch": {"at": [1, 2]}},
                  {"touch": [{"at": [1, 2], "to": "#c8442f", "kind": "plastic"}]}):
        p.write_text(json.dumps({"format": "refinish-touch/1", **touch}), encoding="utf-8")
        r, _ = run("palette.py", "apply", subject, card, tmp_path / "carded.json", "--touch", p)
        assert r.returncode == 2 and "Traceback" not in r.stderr, touch
    p.write_text(json.dumps({"touch": []}), encoding="utf-8")
    r, _ = run("palette.py", "apply", subject, card, tmp_path / "carded.json", "--touch", p)
    assert r.returncode == 2 and "refinish-touch/1" in r.stderr


def test_an_eye_is_split_by_its_iris_shape():
    """A pale grey-blue iris beside a white shaded grey, a dark lash line above: the click lands on the iris, the
    segmenter's round mask there is taken for it, the white is clicked and taken out, and the lashes are the dark that
    is left. Clicked by hand, a click on the white is a click off the iris too."""
    import _eyes
    h, w = 120, 200
    yy, xx = np.mgrid[:h, :w]
    eye = ((xx - 100) / 90.0) ** 2 + ((yy - 62) / 40.0) ** 2 <= 1
    iris = ((xx - 100) ** 2 + (yy - 68) ** 2 <= 34 ** 2) & eye            # (down to the eye's rim: two whites)
    lashes = eye & (yy < 34)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.78, 0.78, 0.80)                                   # the white, shaded grey
    img[iris] = (0.50, 0.58, 0.72)                                # a pale grey-blue iris
    img[lashes] = (0.08, 0.07, 0.08)                              # the lash line
    white_l = eye & ~iris & ~lashes & (xx < 100)
    white_r = eye & ~iris & ~lashes & (xx >= 100)
    calls = []

    def predict(points, labels):
        calls.append((points.copy(), labels.copy()))
        x, y = points[0]
        if iris[int(y), int(x)]:
            return [np.zeros_like(eye), iris, eye], [0.6, 0.9, 0.7]
        side = white_l if white_l[int(y), int(x)] else white_r
        return [side, white_l | white_r, eye], [0.9, 0.6, 0.5]

    got_iris, got_white, got_lash = _eyes.split(predict, img, eye)
    assert (got_iris & iris).sum() / (got_iris | iris).sum() > 0.9
    assert (got_white & (white_l | white_r)).sum() > 0.8 * (white_l | white_r).sum()
    assert (got_lash & lashes).sum() > 0.8 * lashes.sum() and not (got_lash & iris).any()
    assert _eyes.doubts(got_iris, got_white, got_lash, eye) == []
    calls.clear()
    _eyes.split(predict, img, eye, iris_at=[(100, 68)], white_at=[(30, 62)])
    pts, labels = calls[0]
    assert labels.tolist() == [1, 0] and tuple(pts[1]) == (30, 62)


def test_eye_doubts_flag_a_split_that_looks_wrong():
    import _eyes
    eye = np.zeros((100, 100), bool)
    eye[20:80, 10:90] = True
    iris = np.zeros_like(eye)
    iris[30:70, 35:65] = True
    white = np.zeros_like(eye)
    white[30:70, 15:35] = True
    lash = np.zeros_like(eye)
    lash[20:30, 10:90] = True
    assert _eyes.doubts(iris, white, lash, eye) == []
    assert _eyes.doubts(None, white, lash, eye)[0].startswith("no iris")
    speck = np.zeros_like(eye)
    speck[45:55, 45:55] = True
    assert any("small" in d for d in _eyes.doubts(speck, white, lash, eye))
    assert any("lashes" in d for d in _eyes.doubts(iris, white, eye & ~iris & ~white, eye))
    assert any("white" in d for d in _eyes.doubts(iris, np.zeros_like(eye), lash, eye))


def test_a_point_or_within_takes_what_the_parse_holds():
    """The parse holds the head's hair, and a part's growth stops at it; a point placed on a region it holds, or the
    part's within box, takes it (a brush's handle the parse read as hair, in pieces between the fingers)."""
    import auto_parts as ap
    reg = np.zeros((40, 40), np.int32)
    reg[0:10], reg[10:15], reg[15:20], reg[20:40] = 1, 2, 3, 4      # hair, two dark stripes, the white shirt
    n = 5
    lab_ = np.zeros((n, 3))
    lab_[1], lab_[2], lab_[3], lab_[4] = (70, 0, -2), (38, 1, -3), (39, 1, -3), (92, 0, 0)
    ys, xs = np.mgrid[0:40, 0:40]
    st = {"area": np.bincount(reg.ravel(), minlength=n).astype(float), "lab": lab_,
          "cx": np.array([xs[reg == i].mean() if i else 0 for i in range(n)]),
          "cy": np.array([ys[reg == i].mean() if i else 0 for i in range(n)]),
          "box": [(slice(int(ys[reg == i].min()), int(ys[reg == i].max()) + 1),
                   slice(0, 40)) for i in range(1, n)]}
    nb = {1: {2: 40}, 2: {1: 40, 3: 40}, 3: {2: 40, 4: 40}, 4: {3: 40}}
    fig = {"area": 1e6}
    point = [{"name": "stripes", "kind": "cloth-dark", "at": [[20, 12]]}]
    assert ap.claim(point, reg, st, nb, fig, held=[1, 2, 3]) == {2: 0}          # the point's region, no growth
    assert ap.claim(point, reg, st, nb, fig).get(3) == 0                        # (nothing held: it grows)
    sel = [{**point[0], "within": [0, 0, 40, 40]}]
    assert ap.claim(sel, reg, st, nb, fig, held=[1, 2, 3]) == {2: 0, 3: 0}      # the stripes, not the hair
    # a selection is surer than another part's box cut (a generous box round long hair takes the stripes by colour)
    two = [{"name": "hair", "kind": "hair", "at": [[20, 5]]}, sel[0]]
    assert ap.claim(two, reg, st, nb, fig, fixed={3: 0}, held=[1, 2, 3]).get(3) == 1
    # but not a region nearer the cutting part's colour: a selection of white leaves the white shirt's own cut alone
    white = [{"name": "shirt", "kind": "cloth-white", "at": [[20, 30]]},
             {"name": "pick", "kind": "accessory", "at": [[20, 30]], "within": [0, 0, 40, 40]}]
    assert ap.claim(white, reg, st, nb, fig, fixed={4: 0}).get(4) == 0


def test_an_eye_below_the_nose_is_the_mouth():
    """The part segmentation read a laughing mouth as an eye (its teeth a white, its tongue an iris): what it calls an
    eye below the nose goes to the mouth; the eyes above stay, the lower eye of a tilted head too."""
    import seethrough_parse as stp
    P = {p: k + 1 for k, p in enumerate(stp.PARSE_PARTS)}
    lab = np.zeros((300, 300), np.uint8)
    lab[40:260, 60:240] = P["face"]
    lab[100:115, 90:130] = P["eyes"]                                 # an eye
    lab[118:132, 170:210] = P["eyes"]                                # the lower eye of a tilted head
    lab[125:140, 145:155] = P["nose"]
    lab[180:220, 110:190] = P["eyes"]                                # the open mouth, read as an eye
    assert stp.eyes_below_nose(lab) == 1
    assert (lab[180:220, 110:190] == P["mouth"]).all()
    assert (lab[100:115, 90:130] == P["eyes"]).all() and (lab[118:132, 170:210] == P["eyes"]).all()
    lab[lab == P["nose"]] = P["face"]                                # no nose: the face's lowest 30 %
    lab[200:230, 120:180] = P["eyes"]
    assert stp.eyes_below_nose(lab) == 1 and (lab[200:230, 120:180] == P["mouth"]).all()
    lab[280:290, 100:120] = P["eyes"]                                # below the chin: no part of the face
    assert stp.eyes_below_nose(lab) == 1 and (lab[280:290, 100:120] == 0).all()


def test_eyes_file_mistakes_stop(tmp_path):
    import seethrough_parse as stp
    p = tmp_path / "eyes.json"
    for bad in ({"eyes": []}, {"format": "refinish-eyes/1", "eyes": [{"iris": [[1, 2]]}]},
                {"format": "refinish-eyes/1", "eyes": [{"eye": 0}]},
                {"format": "refinish-eyes/1", "eyes": [{"eye": 0, "iris": [1, 2]}]}):
        p.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(SystemExit):
            stp.load_fixes(p)
    p.write_text(json.dumps({"format": "refinish-eyes/1", "eyes": [
        {"eye": 1, "keep": True}, {"eye": 0, "iris": [[5, 6]], "white": [[1, 2]]}]}), encoding="utf-8")
    assert set(stp.load_fixes(p)) == {0, 1}


def test_auto_parts_takes_eyes_a_segmenter_split(hinted, tmp_path):
    """A parse whose eyes a segmenter split (seethrough_parse.py): the irises are taken whole (exact), the whites are a
    part of their own, the eyes are boxed; a card recolours the irises with no RC finding."""
    from _style import load_subject
    from parts import load_or_build
    import auto_parts as ap
    subject, _, at = hinted
    sj = load_subject(subject)
    _, _, parts = load_or_build(sj)
    names = [p["name"] for p in sj["parts"]]

    def of(n):
        return parts == names.index(n) + 1

    parse = np.zeros(parts.shape, np.uint8)
    for n, label in (("jacket", "topwear"), ("trousers", "bottomwear"), ("shoes", "footwear"), ("hair", "hair"),
                     ("mouth", "mouth"), ("irises", "iris"), ("eye-whites", "eye-white")):
        parse[of(n)] = ap.PARSE[label]
    yy = np.arange(parts.shape[0])[:, None]
    parse[of("skin") & (yy < at(0, 290)[1])] = ap.PARSE["face"]
    parse[of("skin") & (yy >= at(0, 290)[1])] = ap.PARSE["handwear"]
    cv2.imwrite(str(tmp_path / "parse.png"), parse)
    hints = json.loads((subject.parent / "hints.json").read_text(encoding="utf-8"))
    hints = {"parts": [q for q in hints["parts"] if q["name"] not in ("hair",)]}
    (tmp_path / "hints.json").write_text(json.dumps(hints), encoding="utf-8")
    r, d = run("auto_parts.py", subject.parent / "image.png", tmp_path / "subject.json", "--upscaled", "2",
               "--hints", tmp_path / "hints.json", "--parse", tmp_path / "parse.png")
    assert r.returncode in (0, 1), r.stderr[-400:]
    got = json.loads((tmp_path / "subject.json").read_text(encoding="utf-8"))
    by = {p["name"]: p for p in got["parts"]}
    assert by["irises"].get("exact") and "eye-whites" in by
    assert len([b for b in got["protect"] if "eye" in b["name"]]) == 2
    # hints naming every part, one of them as the parse's irises: it adds to them (it once dropped them, their
    # regions then in no part)
    ys, xs = np.nonzero(of("irises"))
    full = {"complete": True, "parts": hints["parts"] + [{"name": "irises", "kind": "eyes",
                                                          "at": [[int(xs[0]), int(ys[0])]]}]}
    (tmp_path / "hints2.json").write_text(json.dumps(full), encoding="utf-8")
    r, _ = run("auto_parts.py", subject.parent / "image.png", tmp_path / "subject2.json", "--upscaled", "2",
               "--hints", tmp_path / "hints2.json", "--parse", tmp_path / "parse.png")
    assert r.returncode in (0, 1), r.stderr[-400:]
    by2 = {p["name"]: p for p in json.loads((tmp_path / "subject2.json").read_text(encoding="utf-8"))["parts"]}
    assert by2["irises"].get("exact") and set(by["irises"]["regions"]) <= set(by2["irises"]["regions"])
    assert "eye-whites" in by2
    card = card_file(tmp_path, {"parts": {"jacket": "#2e7d5b"}, "iris": "#d04040"})
    r, _ = run("palette.py", "apply", tmp_path / "subject.json", card, tmp_path / "carded.json")
    assert r.returncode == 0, r.stderr[-400:]
    r, d = run("refinish.py", tmp_path / "carded.json", "tv-cel", tmp_path / "out.png")
    assert r.returncode in (0, 1), r.stderr[-600:]
    assert not [f for f in d["check"]["findings"] if f.startswith("RC3")], d["check"]["findings"]


def test_a_card_that_matches_nothing_changes_nothing(hinted, tmp_path):
    from _core import load_rgba
    subject, plain_png, _ = hinted
    r, d = run("palette.py", "apply", subject, card_file(tmp_path, {"parts": {"no-such-part": "#ff0000"}}),
               tmp_path / "carded.json")
    assert r.returncode == 0 and d["recoloured"] == {}
    r, _ = run("refinish.py", tmp_path / "carded.json", "tv-cel", tmp_path / "out.png", "--no-check")
    assert r.returncode == 0, r.stderr[-400:]
    assert np.array_equal(load_rgba(tmp_path / "out.png")[0], load_rgba(plain_png)[0])
