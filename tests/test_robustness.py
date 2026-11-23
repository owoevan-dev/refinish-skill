"""Broken, hostile and unusual input: a clean message and exit code 2, never a traceback, and nothing the user gave is
changed. A picture may sit in a folder named in any language, and a run that dies leaves the earlier file whole."""
import ast
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib

import cv2
import numpy as np
import pytest

from conftest import SCRIPTS, SKILL, draw_figure

PY = sys.executable
UNICODE_DIR = "角色 テスト 캐릭터"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "OPENCV_LOG_LEVEL": "OFF"}


def cli(script, *args, cwd=None, env=None, codes=(0, 1, 2)):
    r = subprocess.run([PY, str(SCRIPTS / script), *map(str, args)], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env or ENV)
    assert "Traceback" not in r.stderr, f"{script} {args}\n{r.stderr[-1500:]}"
    assert r.returncode in codes, f"{script} {args}: exit {r.returncode}\n{r.stderr[-800:]}"
    return r


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp("base")
    cv2.imwrite(str(d / "image.png"), draw_figure())
    cli("auto_parts.py", "image.png", "subject.json", cwd=d)
    files = {
        "card.json": {"format": "refinish-palette/1", "name": "c", "kinds": {"hair": "#3f5f8a"}, "iris": "#3f9f6a"},
        "touch.json": {"format": "refinish-touch/1", "touch": [{"at": [240, 400], "keep": True}]},
        "recipe.json": {"format": "refinish-recipe/1", "subject": "subject.json", "base": "tv-cel",
                        "layers": [{"style": "watercolour", "where": ["hair"], "opacity": 0.7}],
                        "post": [{"op": "grain", "amount": 0.01}]},
        "outline.json": {"outline": [[[10, 10], [470, 10], [470, 890], [10, 890]]], "band": 16},
        "scene.json": {"frame": [480, 900], "background": {"image": "image.png"},
                       "layers": [{"image": "image.png", "place": [0, 900, 1.0]}]},
        "hints.json": {"complete": False, "parts": [{"name": "hair", "kind": "hair", "at": [[240, 60]]}]},
    }
    for name, value in files.items():
        (d / name).write_text(json.dumps(value), encoding="utf-8")
    shutil.copy(SKILL / "styles" / "tv-cel.json", d / "style.json")
    cli("refinish.py", "subject.json", "style.json", "made.png", "--no-check", cwd=d)
    return d


@pytest.fixture
def work(base, tmp_path):
    d = tmp_path / "w"
    shutil.copytree(base, d)
    return d


# ------------------------------------------------------------------------------------------------ any folder, any name

def test_a_whole_workflow_in_a_folder_named_in_three_languages(tmp_path):
    """On Windows, OpenCV's own file calls cannot open such a path: Refinish did nothing at all for these users."""
    d = tmp_path / UNICODE_DIR
    d.mkdir()
    (d / "圖.png").write_bytes(cv2.imencode(".png", draw_figure())[1].tobytes())
    cli("check_input.py", "圖.png", cwd=d)
    assert cli("prep.py", "圖.png", "大.png", "--scale", "2", cwd=d).returncode == 0
    cli("auto_parts.py", "大.png", "主題.json", cwd=d)
    r = cli("refinish.py", "主題.json", SKILL / "styles" / "tv-cel.json", "完成.png", cwd=d)
    assert json.loads(r.stdout)["out"] == "完成.png"
    assert cv2.imdecode(np.fromfile(str(d / "完成.png"), np.uint8), cv2.IMREAD_UNCHANGED).shape[2] == 4
    (d / "色卡.json").write_text(json.dumps({"format": "refinish-palette/1", "name": "色", "kinds": {"hair": "#3f5f8a"}}),
                                 encoding="utf-8")
    cli("palette.py", "apply", "主題.json", "色卡.json", "換色.json", cwd=d, codes=(0,))
    cli("refinish.py", "換色.json", SKILL / "styles" / "film-everyday-cel.json", "換色.png", cwd=d)
    assert (d / "換色.png").stat().st_size > 1000
    assert cli("zoom.py", "完成.png", "0,0,100,100", "放大.jpg", cwd=d).returncode == 0
    assert (d / "放大.jpg").is_file()


def test_every_other_reader_opens_such_a_folder(tmp_path):
    d = tmp_path / UNICODE_DIR
    d.mkdir()
    fig = cv2.imencode(".png", draw_figure())[1].tobytes()
    (d / "背景.png").write_bytes(fig)
    (d / "場景.json").write_text(json.dumps({"frame": [480, 900], "background": {"image": "背景.png"},
                                            "layers": [{"image": "背景.png", "place": [0, 900, 1.0]}]}), encoding="utf-8")
    assert cli("composite.py", "場景.json", "合成.png", cwd=d).returncode == 0
    (d / "輪廓.json").write_text(json.dumps({"outline": [[[10, 10], [470, 10], [470, 890], [10, 890]]], "band": 16}),
                                 encoding="utf-8")
    cli("cutout.py", "背景.png", "輪廓.json", "切", cwd=d)
    assert (d / "切" / "figure.png").is_file()


def test_output_survives_a_console_that_cannot_show_the_name(tmp_path):
    d = tmp_path / UNICODE_DIR
    d.mkdir()
    (d / "캐릭터.png").write_bytes(cv2.imencode(".png", draw_figure())[1].tobytes())
    env = {**ENV, "PYTHONUTF8": "0", "PYTHONIOENCODING": "ascii"}
    r = cli("check_input.py", "캐릭터.png", cwd=d, env=env)
    assert json.loads(r.stdout)


def test_no_script_uses_the_file_calls_that_break_on_such_paths():
    for p in SCRIPTS.glob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Attribute) and n.attr in ("imread", "imwrite", "imreadmulti"):
                pytest.fail(f"{p.name}:{n.lineno} calls cv2.{n.attr}: use _files.read_picture or write_image")


@pytest.mark.parametrize("flags", [cv2.IMREAD_UNCHANGED, cv2.IMREAD_COLOR, cv2.IMREAD_GRAYSCALE])
@pytest.mark.parametrize("ext,im", [(".png", draw_figure(120, 80)), (".png", (draw_figure(120, 80).astype(np.uint16) * 257)),
                                    (".jpg", draw_figure(120, 80)[..., :3]), (".webp", draw_figure(120, 80))],
                         ids=["png8", "png16", "jpeg", "webp"])
def test_reading_by_bytes_gives_what_imread_gave(tmp_path, ext, im, flags):
    from _files import read_picture
    p = tmp_path / f"a{ext}"
    p.write_bytes(cv2.imencode(ext, im)[1].tobytes())
    assert np.array_equal(read_picture(p, flags), cv2.imread(str(p), flags))


def test_an_oriented_jpeg_reads_as_imread_reads_it(tmp_path):
    from _files import read_picture
    jpg = cv2.imencode(".jpg", draw_figure(60, 40)[..., :3])[1].tobytes()
    tiff = b"MM\0*\0\0\0\x08\0\x01\x01\x12\0\x03\0\0\0\x01\0\x06\0\0\0\0\0\0"            # (orientation 6: turned)
    exif = b"Exif\0\0" + tiff
    p = tmp_path / "turned.jpg"
    p.write_bytes(jpg[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + jpg[2:])
    for flags in (cv2.IMREAD_COLOR, cv2.IMREAD_UNCHANGED):
        assert np.array_equal(read_picture(p, flags), cv2.imread(str(p), flags))


def test_writing_gives_the_encoder_s_exact_bytes(tmp_path):
    from _files import write_image
    im = draw_figure(120, 80)
    write_image(tmp_path / "a.png", im)
    assert (tmp_path / "a.png").read_bytes() == cv2.imencode(".png", im)[1].tobytes()


# -------------------------------------------------------------------------------------------- the user's files are safe

OVERWRITES = [
    ("refinish.py", ["subject.json", "style.json", "image.png"], "image.png"),
    ("refinish.py", ["subject.json", "style.json", "./image.png"], "image.png"),
    ("palette.py", ["apply", "subject.json", "card.json", "subject.json"], "subject.json"),
    ("palette.py", ["apply", "subject.json", "card.json", "card.json"], "card.json"),
    ("prep.py", ["image.png", "image.png"], "image.png"),
    ("repair.py", ["made.png", "made.png"], "made.png"),
    ("zoom.py", ["image.png", "0,0,50,50", "image.png"], "image.png"),
    ("composite.py", ["scene.json", "image.png"], "image.png"),
    ("recipe.py", ["recipe.json", "image.png"], "image.png"),
    ("tweak_style.py", ["style.json", "style.json", "softer shadows"], "style.json"),
    ("auto_parts.py", ["image.png", "subject.json", "--hints", "subject.json"], "subject.json"),
    ("refinish.py", ["subject.json", "style.json", "subject.regions.png"], "subject.regions.png"),
    ("refinish.py", ["subject.json", "style.json", "subject.parts.png"], "subject.parts.png"),
    ("check_output.py", ["subject.json", "made.png", "--json", "made.png"], "made.png"),
]


@pytest.mark.parametrize("script,args,victim", OVERWRITES, ids=[f"{s}:{a[-1]}" for s, a, _ in OVERWRITES])
def test_a_result_never_replaces_an_input(work, script, args, victim):
    before = (work / victim).read_bytes()
    r = cli(script, *args, cwd=work, codes=(2,))
    assert "error:" in r.stderr
    assert (work / victim).read_bytes() == before


def test_a_clash_with_a_side_file_stops_before_anything_is_written(work):
    """The check picture of `render.png` is `render.check.jpg`: here that is the source."""
    cv2.imwrite(str(work / "render.check.jpg"), draw_figure()[..., :3])
    cli("auto_parts.py", "render.check.jpg", "s.json", cwd=work)
    before = (work / "render.check.jpg").read_bytes()
    cli("refinish.py", "s.json", "style.json", "render.png", cwd=work, codes=(2,))
    assert (work / "render.check.jpg").read_bytes() == before and not (work / "render.png").exists()


def test_a_cutout_stops_before_it_replaces_anything(work):
    (work / "cut").mkdir()
    shutil.copy(work / "image.png", work / "cut" / "background.png")
    (work / "cut" / "figure.png").write_bytes(b"earlier")
    cli("cutout.py", "cut/background.png", "outline.json", "cut", cwd=work, codes=(2,))
    assert (work / "cut" / "figure.png").read_bytes() == b"earlier"


def test_no_face_found_leaves_a_picture_named_like_the_face_sheet_alone(tmp_path):
    im = np.full((600, 400, 4), 255, np.uint8)
    im[100:500, 100:300] = (60, 120, 200, 255)
    p = tmp_path / "draft.face.png"
    cv2.imwrite(str(p), im)
    (tmp_path / "draft.face.jpg").write_bytes(cv2.imencode(".jpg", im[..., :3])[1].tobytes())
    before = (tmp_path / "draft.face.jpg").read_bytes()
    r = cli("auto_parts.py", "draft.face.jpg", "draft.json", cwd=tmp_path)
    assert (tmp_path / "draft.face.jpg").read_bytes() == before, r.stderr[-300:]


def test_the_style_fitter_does_not_render_over_a_reference(work):
    (work / "fit").mkdir()
    shutil.copy(work / "made.png", work / "fit" / "start_tv-cel.png")
    before = (work / "fit" / "start_tv-cel.png").read_bytes()
    cli("fit_style.py", "subject.json", "fit/start_tv-cel.png", "--out", "o.json", "--work", "fit", "--start", "tv-cel",
        "--rounds", "1", cwd=work, codes=(2,))
    assert (work / "fit" / "start_tv-cel.png").read_bytes() == before


def test_a_hard_link_to_the_input_is_the_input(work):
    try:
        os.link(work / "image.png", work / "other.png")
    except OSError:
        pytest.skip("no hard links here")
    before = (work / "image.png").read_bytes()
    cli("refinish.py", "subject.json", "style.json", "other.png", cwd=work, codes=(2,))
    assert (work / "image.png").read_bytes() == before


def test_a_link_to_the_input_is_the_input(work):
    try:
        os.symlink(work / "image.png", work / "linked.png")
    except (OSError, NotImplementedError):
        pytest.skip("no symbolic links here")
    before = (work / "image.png").read_bytes()
    cli("refinish.py", "subject.json", "style.json", "linked.png", cwd=work, codes=(2,))
    assert (work / "image.png").read_bytes() == before


def test_running_again_over_its_own_output_is_fine(work):
    cli("refinish.py", "subject.json", "style.json", "again.png", cwd=work)
    cli("refinish.py", "subject.json", "style.json", "again.png", cwd=work)


def test_a_failed_write_leaves_the_earlier_file_whole(tmp_path, monkeypatch):
    import _files
    p = tmp_path / "a.txt"
    p.write_text("earlier", encoding="utf-8")

    def broken(*_):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(_files.os, "replace", broken)
    with pytest.raises(SystemExit) as e:
        _files.write_text(p, "new")
    assert e.value.code == 2 and p.read_text(encoding="utf-8") == "earlier"
    assert [q.name for q in tmp_path.iterdir()] == ["a.txt"]


def test_a_moment_s_file_lock_is_waited_out(tmp_path, monkeypatch):
    import _files
    real, calls = os.replace, []

    def locked(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(13, "in use")
        real(a, b)
    monkeypatch.setattr(_files.os, "replace", locked)
    _files.write_text(tmp_path / "a.txt", "new")
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "new" and len(calls) == 3


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_a_replaced_file_keeps_its_mode_and_a_new_one_follows_the_umask(tmp_path):
    import _files
    p = tmp_path / "a.txt"
    p.write_text("x", encoding="utf-8")
    os.chmod(p, 0o600)
    _files.write_text(p, "y")
    assert p.stat().st_mode & 0o777 == 0o600
    old = os.umask(0o027)
    try:
        _files.write_text(tmp_path / "b.txt", "z")
    finally:
        os.umask(old)
    assert (tmp_path / "b.txt").stat().st_mode & 0o777 == 0o640


def test_writing_does_not_touch_a_file_that_looks_like_its_temporary(tmp_path):
    import _files
    other = tmp_path / f".a.txt.{os.getpid()}.tmp"
    other.write_text("someone else's", encoding="utf-8")
    _files.write_text(tmp_path / "a.txt", "new")
    assert other.read_text(encoding="utf-8") == "someone else's"


def test_a_stale_part_cache_with_bad_numbers_is_rebuilt(work):
    from _style import load_subject
    from parts import load_or_build, parts_path
    sj = load_subject(work / "subject.json")
    good = load_or_build(sj)[2]
    bad = np.full_like(good, len(sj["parts"]) + 7)
    cv2.imwrite(str(parts_path(sj)), bad)
    assert np.array_equal(load_or_build(sj)[2], good)


# ------------------------------------------------------------------------------------------------------- broken pictures

def png_claiming(w, h):
    def chunk(k, b):
        return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(b"\0" * 100)) + chunk(b"IEND", b"")


@pytest.mark.parametrize("ext,im", [(".png", (70, 40)), (".jpg", (70, 40)), (".webp", (70, 40))])
def test_the_size_is_read_from_the_header(ext, im):
    from _files import picture_size
    data = cv2.imencode(ext, np.zeros((im[1], im[0], 3), np.uint8))[1]
    assert picture_size(data) == im


@pytest.mark.parametrize("w,h", [(30000, 30000), (2 ** 31 - 1, 1), (10001, 10001)])
def test_a_picture_claiming_too_many_pixels_is_refused_before_decoding(tmp_path, w, h):
    p = tmp_path / "bomb.png"
    p.write_bytes(png_claiming(w, h))
    r = cli("check_input.py", p, codes=(2,))
    assert "pixels" in r.stderr


def bad_pictures():
    fig = draw_figure(200, 120)
    good = cv2.imencode(".png", fig)[1].tobytes()
    solid = lambda h, w, a: np.dstack([np.full((h, w, 3), 200, np.uint8), np.full((h, w), a, np.uint8)])
    return {"empty": b"", "text": b"not a picture", "truncated": good[:len(good) // 3], "header": good[:33],
            "1x1": cv2.imencode(".png", solid(1, 1, 255))[1].tobytes(),
            "3x3": cv2.imencode(".png", solid(3, 3, 255))[1].tobytes(),
            "line": cv2.imencode(".png", solid(400, 1, 255))[1].tobytes(),
            "transparent": cv2.imencode(".png", solid(100, 60, 0))[1].tobytes(),
            "gray16": cv2.imencode(".png", fig[..., 0].astype(np.uint16) * 257)[1].tobytes()}


PICTURE_COMMANDS = [("check_input.py", ["x.png"]), ("prep.py", ["x.png", "o.png"]), ("auto_parts.py", ["x.png", "o.json"]),
                    ("scene_subject.py", ["x.png", "o.json"]), ("zoom.py", ["x.png", "0,0,50,50", "o.jpg"]),
                    ("repair.py", ["x.png", "o.png"]), ("measure_style.py", ["x.png"]),
                    ("hints.py", ["pick", "x.png", "0,0,50,50"]), ("palette.py", ["read", "x.png"])]


@pytest.mark.parametrize("name", list(bad_pictures()))
def test_broken_pictures_get_a_clean_answer(tmp_path, name):
    (tmp_path / "x.png").write_bytes(bad_pictures()[name])
    for script, args in PICTURE_COMMANDS:
        cli(script, *args, cwd=tmp_path)


# ---------------------------------------------------------------------------------------------------------- broken JSON

@pytest.mark.parametrize("data", [b"", b"not json", b'{"a": "\xff\xfe"}', b"[" * 200000, b'{"a": NaN}', b'{"a": Infinity}',
                                  b'{"a": 1e999}', b'{"a": [1, -Infinity]}'],
                         ids=["empty", "text", "bad-utf8", "deep", "nan", "inf", "huge", "nested-inf"])
def test_broken_json_is_refused(tmp_path, data):
    from _files import read_json
    p = tmp_path / "a.json"
    p.write_bytes(data)
    with pytest.raises(SystemExit) as e:
        read_json(p)
    assert e.value.code == 2


def test_a_byte_order_mark_is_fine(tmp_path):
    from _files import read_json
    p = tmp_path / "a.json"
    p.write_bytes(b'\xef\xbb\xbf{"a": 1}')
    assert read_json(p) == {"a": 1}


def test_an_oversized_json_is_refused(tmp_path, monkeypatch):
    import _files
    monkeypatch.setattr(_files, "MAX_JSON_BYTES", 8)
    p = tmp_path / "a.json"
    p.write_text('{"a": 1234567}', encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        _files.read_json(p)
    assert e.value.code == 2


JSON_COMMANDS = {
    "subject": [("refinish.py", ["x.json", "style.json", "o.png"]), ("parts.py", ["x.json"]), ("check_input.py", ["x.json"]),
                ("palette.py", ["apply", "x.json", "card.json", "o.json"]), ("check_output.py", ["x.json", "made.png"])],
    "style": [("refinish.py", ["subject.json", "x.json", "o.png"]), ("tweak_style.py", ["x.json", "o.json", "softer shadows"])],
    "card": [("palette.py", ["apply", "subject.json", "x.json", "o.json"]), ("palette.py", ["board", "x.json", "o.png"])],
    "touch": [("palette.py", ["apply", "subject.json", "card.json", "o.json", "--touch", "x.json"])],
    "hints": [("auto_parts.py", ["image.png", "o.json", "--hints", "x.json"]), ("hints.py", ["check", "x.json", "subject.json"])],
    "outline": [("cutout.py", ["image.png", "x.json", "od"])],
    "recipe": [("recipe.py", ["x.json", "o.png"])],
    "scene": [("composite.py", ["x.json", "o.png"])],
}


@pytest.mark.parametrize("slot", JSON_COMMANDS)
@pytest.mark.parametrize("data", [b"null", b"[]", b"0", b'"x"', b"{}", b"\xff\xfe"], ids=["null", "list", "zero", "text", "object", "bad"])
def test_a_wrong_file_in_each_slot_is_refused(work, slot, data):
    (work / "x.json").write_bytes(data)
    for script, args in JSON_COMMANDS[slot]:
        r = cli(script, *args, cwd=work, codes=(0, 1, 2))
        if data != b"{}" or slot not in ("card", "hints"):
            assert r.returncode == 2 and "error" in r.stderr, (script, data)


VALUES = [None, 0, -1, 1.5, "x", "", [], {}, [1], [[1, 2]], {"a": 1}, True, "../../outside.png"]


def mutations(obj):
    """Every field, and the fields of each list's first object, removed or replaced."""
    for k in obj:
        d = json.loads(json.dumps(obj))
        del d[k]
        yield f"-{k}", d
        for v in VALUES:
            d = json.loads(json.dumps(obj))
            d[k] = v
            yield f"{k}={v!r}", d
        if isinstance(obj[k], list) and obj[k] and isinstance(obj[k][0], dict):
            for f in obj[k][0]:
                for v in VALUES:
                    d = json.loads(json.dumps(obj))
                    d[k][0][f] = v
                    yield f"{k}[0].{f}={v!r}", d


@pytest.mark.parametrize("kind", ["subject", "hints", "outline", "recipe", "scene", "style"])
def test_the_validators_accept_or_refuse_but_never_break(base, kind):
    import _validate
    file = {"style": "style.json"}.get(kind, f"{kind}.json")
    good = json.loads((base / file).read_text(encoding="utf-8"))
    check = {"subject": _validate.subject, "hints": _validate.hints, "outline": _validate.outline, "scene": _validate.scene,
             "recipe": _validate.recipe, "style": _validate.style}[kind]
    check(good, file)
    refused = 0
    for name, d in mutations(good):
        try:
            check(d, file)
        except SystemExit as e:
            assert e.code == 2, name
            refused += 1
    assert refused >= 10


@pytest.mark.parametrize("field,value", [("image", 7), ("regions", ["a"]), ("parts", 3), ("protect", [{"name": "e"}]),
                                         ("focal", [{"centre": 1, "radii": [1, 1]}]), ("blush", [[1, 2]]), ("upscaled", "2"),
                                         ("follow", "up"), ("rules", 4), ("head_px", -1)])
def test_a_wrong_subject_field_is_named(work, field, value):
    d = json.loads((work / "subject.json").read_text(encoding="utf-8"))
    d[field] = value
    (work / "x.json").write_text(json.dumps(d), encoding="utf-8")
    r = cli("refinish.py", "x.json", "style.json", "o.png", cwd=work, codes=(2,))
    assert field in r.stderr


@pytest.mark.parametrize("extra", [{"print": {"inks": [[50, 20, 30], [80, 0, 0]]}}, {"sticker": {"edge": None}},
                                   {"duotone": {"stops": ["#101820", "#f2e9dc"]}},
                                   {"post": [{"op": "curve", "lift": 0.03}]},
                                   {"post": [{"op": "curve", "gain": [1, 0.98, 0.95]}]}], ids=lambda e: next(iter(e)))
def test_what_the_style_format_documents_is_accepted(extra):
    import _validate
    _validate.style({"format": "refinish-style/1", "engine": "cel", **extra}, "custom.json")


@pytest.mark.parametrize("extra", [{"shading": 3}, {"post": [{"op": "curve", "lift": [0, 1]}]}, {"post": "grain"}],
                         ids=["section", "curve", "post"])
def test_a_wrong_style_shape_is_refused(extra):
    import _validate
    with pytest.raises(SystemExit) as e:
        _validate.style({"format": "refinish-style/1", "engine": "cel", **extra}, "custom.json")
    assert e.value.code == 2


def test_results_do_not_name_the_folders_above_them(work):
    marker = work.parent.name
    (work / "a").mkdir()
    (work / "b").mkdir()
    shutil.copy(work / "image.png", work / "a" / "image.png")
    cli("auto_parts.py", "a/image.png", "a/subject.json", cwd=work)
    cli("palette.py", "apply", "a/subject.json", "card.json", "b/carded.json", cwd=work, codes=(0,))
    cli("measure_style.py", "a/image.png", "--out", "b/metrics.json", cwd=work)
    for name in ("b/carded.json", "b/metrics.json"):
        assert marker not in (work / name).read_text(encoding="utf-8"), name


def test_a_style_cannot_name_a_module(work):
    d = json.loads((work / "style.json").read_text(encoding="utf-8"))
    for engine in ("os", "subprocess", "../evil", "_core"):
        d["engine"] = engine
        (work / "x.json").write_text(json.dumps(d), encoding="utf-8")
        assert "engine" in cli("refinish.py", "subject.json", "x.json", "o.png", cwd=work, codes=(2,)).stderr


def test_a_post_layer_must_be_a_known_operation(work):
    d = json.loads((work / "recipe.json").read_text(encoding="utf-8"))
    d["post"] = [{"op": "__import__"}]
    (work / "x.json").write_text(json.dumps(d), encoding="utf-8")
    assert "post[0].op" in cli("recipe.py", "x.json", "o.png", cwd=work, codes=(2,)).stderr


@pytest.mark.parametrize("flag,value", [("--families", 0), ("--families", 100000)])
def test_scene_subject_refuses_impossible_settings(work, flag, value):
    cli("scene_subject.py", "image.png", "o.json", flag, value, cwd=work, codes=(2,))


# --------------------------------------------------------------------------------------------------------- exit codes

def test_an_unexpected_error_is_not_read_as_done_with_doubts(capsys):
    from _files import run_cli

    def boom():
        raise ValueError("a surprise")
    with pytest.raises(SystemExit) as e:
        run_cli(boom)
    err = capsys.readouterr().err
    assert e.value.code == 3 and "ValueError" in err and "Traceback" not in err and "report" in err
    assert "a surprise" not in err                      # (a message can quote a path; this line is meant to be shared)


def test_debug_mode_shows_the_traceback(capsys, monkeypatch):
    from _files import run_cli
    monkeypatch.setenv("REFINISH_DEBUG", "1")

    def boom():
        raise KeyError("a surprise")
    with pytest.raises(SystemExit):
        run_cli(boom)
    assert "Traceback" in capsys.readouterr().err


@pytest.mark.parametrize("error,code", [(OSError(13, "denied", "x.png"), 2), (MemoryError(), 2), (RecursionError(), 2)])
def test_what_the_user_can_fix_is_a_bad_input(error, code):
    from _files import run_cli

    def boom():
        raise error
    with pytest.raises(SystemExit) as e:
        run_cli(boom)
    assert e.value.code == code


def test_run_cli_passes_an_exit_through():
    from _files import run_cli

    def done():
        sys.exit(1)
    with pytest.raises(SystemExit) as e:
        run_cli(done)
    assert e.value.code == 1


def test_every_script_runs_under_the_guard():
    for p in SCRIPTS.glob("*.py"):
        t = p.read_text(encoding="utf-8")
        if '__name__ == "__main__"' in t and p.name not in ("check_env.py", "png_note.py"):
            assert "run_cli(main)" in t, p.name
