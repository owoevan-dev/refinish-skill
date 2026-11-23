"""The privacy scan works, the repository passes it, and running the skill keeps what it should to itself."""
import ast
import hashlib
import json
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np
import pytest

import privacy_scan as ps
from conftest import ROOT, SCRIPTS, SKILL, draw_figure

# Every sample is put together at run time, so that this file passes the scan it tests.
U = "Us" + "ers"
SAMPLES = {
    "path-windows": "see C" + ":\\work\\pictures",
    "path-unc": "at \\" + "\\nas01\\share",
    "path-user": f"/{U}/someone/art",
    "path-root": "in /" + "root/project/",
    "path-secret-dir": "copy ~/." + "ssh/config",
    "agent-state": "from ~/.claude" + "/projects/x",
    "workspace-path": "skill-work" + "space/notes",
    "session-id": "run 7609ab12" + "-27ab-4663-908f-6ab5f67fb42f",
    "email": "write to someone" + "@example.org",
    "phone-tw": "call 09" + "12-345-678",
    "national-id-tw": "id A1" + "23456789",
    "card-number": "4111 1111" + " 1111 1111",
    "ip-private": "host 192." + "168.1.20",
    "mac-address": "aa:bb" + ":cc:dd:ee:ff",
    "key-private": "-" * 5 + "BEGIN RSA PRIVATE" + " KEY" + "-" * 5,
    "key-aws": "AKIA" + "IOSFODNN7EXAMPL1",
    "key-github": "ghp_" + "a1B2" * 10,
    "key-anthropic": "sk-ant" + "-api03-" + "a1B2c3" * 5,
    "key-openai": "sk-" + "proj-" + "a1B2c3" * 5,
    "key-google": "AIza" + "a1B2c3D4e5" * 3 + "a1B2c",
    "key-slack": "xox" + "b-1234567890-abcdefghij",
    "webhook": "hooks.slack" + ".com/services/T000/B000/abc",
    "key-huggingface": "hf_" + "a1B2c3D4e5" * 4,
    "key-npm": "npm_" + "a1B2c3" * 6,
    "key-pypi": "pypi-" + "AgE" + "a1B2c3D4" * 7,
    "key-stripe": "sk_" + "live_" + "a1B2c3D4" * 3,
    "key-sendgrid": "SG." + "a1B2c3D4" * 3 + "." + "a1B2c3D4" * 5,
    "key-telegram": "123456789:" + "AA" + "a1B2c3D4e5F" * 3,
    "token-jwt": "eyJ" + "hbGciOiJIUzI1" + ".eyJ" + "zdWIiOiIxMjM0" + ".a1B2c3D4e5f6",
    "url-credentials": "https://" + "someone:hunter2" + "@host.example/x",
    "token-bearer": "Authorization: Bearer " + "a1B2c3D4e5" * 3,
    "secret-assigned": "api_key" + " = 'q7Zp2Lm9Xc4Rt8Vb'",
    "token-random": "x " + "Qm9vZ1B7cX2vT4nL" + "8sK3jH6fD1aW5eR0" + " y",
}
CLEAN = [
    "A girl with long hair and a mustard cardigan.",
    "numpy==2.5.5; python_version >= \"3.12\"",
    "version 10.0.26300 of the system",
    "actions/checkout" + "@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "def fix_bleed(img, alpha, U, parts, names, line, protect, reach=None, margin=6.0):",
    "a colour step of 12.5 and a box of [120, 340, 560, 780]",
    "token = load_token(path)",
    "secret_santa_list_of_names_goes_here",
    "@pytest.mark.parametrize(\"skill\", SKILLS)",
    "https://github.com/owoevan-dev/refinish-skill/issues",
    "/plugin install refinish-skill" + "@refinish-skill",
    "sha256 48b2c3b840dba85b8db191b51cae3d18afc917071cdcb831e5a7319d5c0ca3fb",
    "1234 5678 9012 3456",
    "--hash=sha256:ab" + "241111111111111" + "cd0912345678ef" + "aa" * 18,
]


def rules(text, **kw):
    return {f.rule for f in ps.scan_text(text, "sample", **kw)}


def test_every_rule_has_a_sample():
    assert set(SAMPLES) == {r for r, _, _ in ps.TEXT_RULES}


@pytest.mark.parametrize("rule", sorted(SAMPLES))
def test_rule_finds_its_sample(rule):
    assert rule in rules(SAMPLES[rule]), SAMPLES[rule]


@pytest.mark.parametrize("rule", sorted(SAMPLES))
def test_the_report_never_prints_what_it_found(rule):
    sample = SAMPLES[rule]
    for f in ps.scan_text(sample, "sample"):
        shown = str(f)
        assert sample not in shown and (len(sample) < 12 or sample[3:] not in shown)


@pytest.mark.parametrize("text", CLEAN)
def test_ordinary_text_passes(text):
    assert not rules(text), text


def test_a_rule_finds_a_key_behind_a_line_separator():
    assert "key-github" in rules("harmless" + chr(0x2028) + SAMPLES["key-github"])


def test_private_terms_match_any_case_and_stay_out_of_the_report():
    found = ps.scan_text("made in the SECRET-Project folder", "sample", terms=["secret-project"])
    assert [f.rule for f in found] == ["private-term"] and "secret" not in str(found[0]).lower().replace("sample", "")


def test_private_terms_are_found_in_a_picture_s_bytes():
    png = cv2.imencode(".png", np.zeros((4, 4, 3), np.uint8))[1].tobytes()
    data = png[:-12] + "秘密案子".encode("utf-16-le") + png[-12:]
    assert "private-term" in {f.rule for f in ps.scan_blob(data, "a.png", ["秘密案子"])}


# ------------------------------------------------------------------------------------------------- what a picture holds

def plain_png():
    return cv2.imencode(".png", np.full((6, 6, 3), 120, np.uint8))[1].tobytes()


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def with_chunk(kind, body):
    png = plain_png()
    return png[:33] + chunk(kind, body) + png[33:]


def test_a_plain_png_passes():
    assert ps.scan_image(plain_png(), "a.png") == []


@pytest.mark.parametrize("kind,body", [
    (b"tEXt", b"Software\0some editor"),
    (b"zTXt", b"Comment\0\0" + zlib.compress(b"a note")),
    (b"iTXt", b"XML:com.adobe.xmp\0\0\0\0\0<x:xmpmeta/>"),
    (b"eXIf", b"MM\0*\0\0\0\x08\0\0"),
    (b"caBX", b"c2pa manifest"),
    (b"tIME", b"\x07\xea\x0b\x18\x0c\0\0"),
])
def test_png_metadata_is_found(kind, body):
    assert "image-metadata" in {f.rule for f in ps.scan_image(with_chunk(kind, body), "a.png")}


@pytest.mark.parametrize("kind", [b"tEXt", b"zTXt", b"iTXt"])
def test_png_text_is_read_for_paths(kind):
    text = SAMPLES["path-user"].encode()
    body = {b"tEXt": b"Source\0" + text, b"zTXt": b"Source\0\0" + zlib.compress(text),
            b"iTXt": b"Source\0\0\0\0\0" + text}[kind]
    assert "path-user" in {f.rule for f in ps.scan_image(with_chunk(kind, body), "a.png")}


def test_data_after_the_picture_is_found():
    assert "image-trailing-data" in {f.rule for f in ps.scan_image(plain_png() + b"hidden", "a.png")}
    jpg = cv2.imencode(".jpg", np.full((16, 16, 3), 120, np.uint8))[1].tobytes()
    assert "image-trailing-data" in {f.rule for f in ps.scan_image(jpg + b"hidden", "a.jpg")}


def jpeg_with(marker, body):
    jpg = cv2.imencode(".jpg", np.full((16, 16, 3), 120, np.uint8))[1].tobytes()
    return jpg[:2] + bytes((0xFF, marker)) + struct.pack(">H", len(body) + 2) + body + jpg[2:]


def test_a_plain_jpeg_passes():
    assert ps.scan_image(cv2.imencode(".jpg", np.full((16, 16, 3), 120, np.uint8))[1].tobytes(), "a.jpg") == []


@pytest.mark.parametrize("marker,body", [(0xE1, b"Exif\0\0MM\0*"), (0xE1, b"http://ns.adobe.com/xap/1.0/\0<x/>"),
                                         (0xED, b"Photoshop 3.0\0"), (0xFE, b"a comment")])
def test_jpeg_metadata_is_found(marker, body):
    assert "image-metadata" in {f.rule for f in ps.scan_image(jpeg_with(marker, body), "a.jpg")}


def webp_with(kind, body):
    payload = b"WEBP" + b"VP8L" + struct.pack("<I", 2) + b"\0\0" + kind + struct.pack("<I", len(body)) + body
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


@pytest.mark.parametrize("kind", [b"EXIF", b"XMP "])
def test_webp_metadata_is_found(kind):
    assert "image-metadata" in {f.rule for f in ps.scan_image(webp_with(kind, b"some"), "a.webp")}


@pytest.mark.parametrize("text,rule", [
    ('<svg><script>x()</script></svg>', "svg-script"),
    ('<svg onload="x()"></svg>', "svg-handler"),
    ('<svg><metadata>made by</metadata></svg>', "svg-editor-data"),
    ('<svg><!-- exported --></svg>', "svg-editor-data"),
    ('<svg sodipodi:docname="x.svg"></svg>', "svg-editor-data"),
    ('<svg><image href="https://example.org/a.png"/></svg>', "svg-external"),
    ('<svg><image href="data:image/png;base64,AAAA"/></svg>', "svg-embedded-data"),
])
def test_active_or_revealing_svg_is_found(text, rule):
    assert rule in {f.rule for f in ps.scan_svg(text, "a.svg")}


def test_a_plain_svg_passes():
    assert not ps.scan_svg('<svg viewBox="0 0 8 8"><use href="#a"/><path d="M0 0h8"/></svg>', "a.svg")


@pytest.mark.parametrize("name", [".env", ".env.local", "id_rsa", "server.pem", "auth.json", "credentials.json",
                                  ".claude/settings.local.json", "x-work" + "space/a.txt", "state_5.sqlite", "run.log",
                                  "notes.ipynb", ".npmrc", "Thumbs.db"])
def test_forbidden_names(name):
    assert ps.scan_name(name)


@pytest.mark.parametrize("name", ["README.md", "skills/refinish/styles/tv-cel.json", "tests/test_privacy.py",
                                  "skills/refinish/scripts/hints.py", "LICENSE", ".gitignore"])
def test_ordinary_names(name):
    assert not ps.scan_name(name)


# ------------------------------------------------------------------------------------------------------- the repository

def test_the_repository_passes_the_scan():
    found = ps.scan_tree()
    assert not found, "\n".join(map(str, found[:40]))


def test_every_picture_was_approved():
    """A picture joins the repository only with its hash in tests/public_images.sha256, after a person has looked at it."""
    listed = ps.approved_images()
    for rel in ps.tracked_files():
        if Path(rel).suffix.lower() in ps.IMAGE:
            assert listed.get(rel) == hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), rel


def git_repo(path, email="1+someone" + "@users.noreply.github.com"):
    env = {**os.environ, "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": "a",
           "GIT_COMMITTER_EMAIL": email, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

    def g(*args):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, env=env)
    g("init", "-q")
    return g


def test_history_scan_finds_a_key_deleted_long_ago(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    (tmp_path / "a.txt").write_text(SAMPLES["key-github"] + "\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "first")
    (tmp_path / "a.txt").write_text("clean\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "second")
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    found, commits, _ = ps.scan_history()
    assert commits == 2 and "key-github" in {f.rule for f in found}


def test_history_scan_finds_a_real_address_in_a_commit(tmp_path, monkeypatch):
    g = git_repo(tmp_path, email="someone" + "@example.org")
    (tmp_path / "a.txt").write_text("clean\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "first")
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    assert "commit-email" in {f.rule for f in ps.scan_history()[0]}


def test_history_scan_finds_a_path_in_a_message_and_a_forbidden_file(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "fix " + SAMPLES["path-user"])
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    assert {"path-user", "forbidden-file"} <= {f.rule for f in ps.scan_history()[0]}


def test_history_scan_allows_a_no_reply_co_author(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("clean\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "first\n\nCo-Authored-By: Claude <noreply" + "@anthropic.com>")
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    assert not ps.scan_history()[0]


def test_a_draft_is_scanned(tmp_path):
    """A pull request or release note is checked before it is published."""
    draft = tmp_path / "body.md"
    draft.write_text("Fixes the path " + SAMPLES["path-user"] + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tests" / "privacy_scan.py"), "--draft", str(draft)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1 and "path-user: draft body.md" in r.stdout and SAMPLES["path-user"] not in r.stdout


def test_scan_exit_codes(tmp_path):
    missing = str(tmp_path / "no-such-file")
    r = subprocess.run([sys.executable, str(ROOT / "tests" / "privacy_scan.py"), "--terms", missing],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "could not run" in r.stderr


# --------------------------------------------------------------------------------------------------- the running skill

NETWORK = {"socket", "ssl", "http", "urllib", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "poplib", "imaplib",
           "telnetlib", "xmlrpc", "websocket", "websockets", "paramiko", "boto3", "huggingface_hub"}
RUNS_CODE = {"pickle", "marshal", "shelve", "dill", "cloudpickle"}


def shipped_scripts():
    return sorted(SCRIPTS.glob("*.py"))


def imports(tree):
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    return names | {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}


@pytest.mark.parametrize("script", shipped_scripts(), ids=lambda p: p.name)
def test_scripts_import_nothing_that_talks_to_a_network(script):
    assert not imports(ast.parse(script.read_text(encoding="utf-8"))) & NETWORK


@pytest.mark.parametrize("script", shipped_scripts(), ids=lambda p: p.name)
def test_scripts_never_run_code_from_their_inputs(script):
    tree = ast.parse(script.read_text(encoding="utf-8"))
    assert not imports(tree) & RUNS_CODE
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            bare = name if isinstance(f, ast.Name) else ""
            assert bare not in ("eval", "exec", "compile"), (script.name, n.lineno)
            assert name not in ("system", "popen"), (script.name, n.lineno)
            if bare == "__import__":                    # only names from a fixed table in the script, never from a file
                assert script.name in ("refinish.py", "check_env.py"), (script.name, n.lineno)
            assert not any(k.arg == "shell" for k in n.keywords), (script.name, n.lineno)
            if name == "load" and isinstance(f, ast.Attribute) and getattr(f.value, "id", "") == "yaml":
                pytest.fail(f"{script.name}:{n.lineno} yaml.load")
            if name == "load" and isinstance(f, ast.Attribute) and getattr(f.value, "id", "") == "np":
                assert not any(k.arg == "allow_pickle" for k in n.keywords), (script.name, n.lineno)


def test_only_the_style_fitter_starts_a_process():
    """It runs refinish.py beside it. Everything else stays in one process."""
    users = {p.name for p in shipped_scripts() if "subprocess" in imports(ast.parse(p.read_text(encoding="utf-8")))}
    assert users <= {"fit_style.py", "check_env.py"}, users


GUARD = """
import runpy, socket, sys
def refuse(*a, **k):
    raise RuntimeError("a network call")
socket.socket = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse
sys.argv = sys.argv[1:]
sys.path.insert(0, sys.argv[0].rsplit('/', 1)[0])
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def no_network(script, *args, cwd=None):
    r = subprocess.run([sys.executable, "-c", GUARD, (SCRIPTS / script).as_posix(), *map(str, args)], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert "a network call" not in r.stderr and "Traceback" not in r.stderr, r.stderr[-800:]
    assert r.returncode in (0, 1), r.stderr[-800:]
    return r


@pytest.fixture(scope="module")
def private_run(tmp_path_factory):
    """The whole workflow, with no network, in a folder whose name no output has any reason to carry."""
    marker = "marker_private_folder_q7z"
    d = tmp_path_factory.mktemp("run") / marker
    d.mkdir()
    cv2.imwrite(str(d / "drawn.png"), draw_figure())
    no_network("check_input.py", "drawn.png", cwd=d)
    no_network("prep.py", "drawn.png", "image.png", "--scale", "2", cwd=d)
    no_network("auto_parts.py", "image.png", "subject.json", cwd=d)
    no_network("refinish.py", "subject.json", SKILL / "styles" / "tv-cel.json", "cel.png", cwd=d)
    (d / "card.json").write_text(json.dumps({"format": "refinish-palette/1", "name": "t", "kinds": {"hair": "#3f5f8a"}}),
                                 encoding="utf-8")
    no_network("palette.py", "apply", "subject.json", "card.json", "carded.json", cwd=d)
    no_network("refinish.py", "carded.json", SKILL / "styles" / "film-everyday-cel.json", "recoloured.png", cwd=d)
    return d, marker


def test_the_workflow_runs_with_the_network_cut(private_run):
    assert (private_run[0] / "recoloured.png").stat().st_size > 1000


def test_pictures_it_writes_carry_no_metadata(private_run):
    d, _ = private_run
    pics = [p for p in d.iterdir() if p.suffix in (".png", ".jpg")]
    assert len(pics) >= 5
    for p in pics:
        assert ps.scan_image(p.read_bytes(), p.name) == [], p.name


def test_files_it_writes_do_not_name_the_folder(private_run):
    """A subject or a picture passed to someone else says nothing of where it was made."""
    d, marker = private_run
    leaks = [p.name for p in d.iterdir() if p.is_file() and marker.encode() in p.read_bytes()]
    assert not leaks, leaks
