"""The privacy scan works, the repository passes it, and running the skill keeps what it should to itself."""
import ast
import hashlib
import io
import json
import os
import shutil
import socket
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
    assert [f.rule for f in found] == ["private-term"] and "secret" not in str(found[0]).lower()


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
    assert r.returncode == 1 and "path-user: item " in r.stdout and SAMPLES["path-user"] not in r.stdout


def test_scan_exit_codes(tmp_path):
    missing = str(tmp_path / "private_folder_marker" / "no-such-file")
    r = subprocess.run([sys.executable, str(ROOT / "tests" / "privacy_scan.py"), "--terms", missing],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "could not run" in r.stderr and "private_folder_marker" not in r.stdout + r.stderr


# ------------------------------------------------------------------------------- what the first version of the scan missed

CANARY = "canary" + "marker"


def repo_with_scanner(path):
    """A repository carrying this scanner, as CI runs it."""
    g = git_repo(path)
    (path / "tests").mkdir()
    shutil.copy(ROOT / "tests" / "privacy_scan.py", path / "tests" / "privacy_scan.py")
    g("add", ".")
    g("commit", "-qm", "the scanner")
    return g


def run_scan(path, *args):
    return subprocess.run([sys.executable, str(path / "tests" / "privacy_scan.py"), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


@pytest.mark.parametrize("extra", [[], ["--json"]], ids=["text", "json"])
def test_a_private_name_never_reaches_the_public_report(tmp_path, extra):
    g = repo_with_scanner(tmp_path)
    (tmp_path / CANARY).mkdir()
    (tmp_path / CANARY / ".env").write_text("A=" + SAMPLES["key-github"] + "\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "oops")
    r = run_scan(tmp_path, "--history", *extra)
    assert r.returncode == 1 and "forbidden-file" in r.stdout
    assert CANARY not in r.stdout + r.stderr and SAMPLES["key-github"] not in r.stdout + r.stderr


def test_show_paths_is_for_the_maintainer_s_own_terminal(tmp_path):
    g = repo_with_scanner(tmp_path)
    (tmp_path / CANARY).mkdir()
    (tmp_path / CANARY / ".env").write_text("A=1\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "oops")
    assert CANARY in run_scan(tmp_path, "--show-paths").stdout


def history_rules(path, monkeypatch, terms=(), unreachable=False):
    monkeypatch.setattr(ps, "ROOT", path)
    return {f.rule for f in ps.scan_history(terms, unreachable)[0]}


def commit_text(g, path, name, text):
    (path / name).parent.mkdir(parents=True, exist_ok=True)
    (path / name).write_text(text, encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "c")


def test_history_reads_git_notes(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    commit_text(g, tmp_path, "a.txt", "clean\n")
    g("notes", "add", "-m", SAMPLES["key-github"])
    assert "key-github" in history_rules(tmp_path, monkeypatch)


def test_history_reads_branch_names(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    commit_text(g, tmp_path, "a.txt", "clean\n")
    g("branch", f"feature/{CANARY}")
    assert "private-term" in history_rules(tmp_path, monkeypatch, [CANARY])


def test_history_reads_a_tagger_s_name_and_a_tag_inside_a_tag(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    commit_text(g, tmp_path, "a.txt", "clean\n")
    env = {**os.environ, "GIT_COMMITTER_NAME": CANARY, "GIT_COMMITTER_EMAIL": "1+a" + "@users.noreply.github.com"}
    subprocess.run(["git", "-C", str(tmp_path), "tag", "-a", "inner", "-m", "x"], check=True, env=env)
    g("tag", "-a", "outer", "inner", "-m", "y")
    g("tag", "-d", "inner")
    assert "private-term" in history_rules(tmp_path, monkeypatch, [CANARY])


def test_history_reads_a_commit_nothing_points_at(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    commit_text(g, tmp_path, "a.txt", "clean\n")
    commit_text(g, tmp_path, "b.txt", SAMPLES["key-github"] + "\n")
    g("reset", "-q", "--hard", "HEAD~1")
    g("reflog", "expire", "--expire=now", "--all")
    assert "key-github" not in history_rules(tmp_path, monkeypatch)        # (a push cannot carry it)
    assert "key-github" in history_rules(tmp_path, monkeypatch, unreachable=True)


def test_history_keeps_a_forbidden_name_behind_identical_bytes(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    commit_text(g, tmp_path, "readme.txt", "same\n")
    commit_text(g, tmp_path, ".env", "same\n")
    assert "forbidden-file" in history_rules(tmp_path, monkeypatch)


def test_history_reads_a_private_word_in_a_file_name(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    commit_text(g, tmp_path, f"docs/{CANARY}.md", "clean\n")
    assert "private-term" in history_rules(tmp_path, monkeypatch, [CANARY])


@pytest.mark.parametrize("data,rule", [("contact ".encode("utf-16") + SAMPLES["email"].encode("utf-16-le"), "email"),
                                       (b"PK\x03\x04" + b"\0" * 40, "unreadable-file"),
                                       (b"II*\0" + b"\0" * 40, "unreadable-file"),
                                       (b"abc\0def", "binary-file")], ids=["utf16", "zip", "tiff", "binary"])
def test_history_does_not_forgive_what_it_cannot_read(tmp_path, monkeypatch, data, rule):
    g = git_repo(tmp_path)
    (tmp_path / "old.dat").write_bytes(data)
    g("add", ".")
    g("commit", "-qm", "c")
    g("rm", "-q", "old.dat")
    g("commit", "-qm", "d")
    assert rule in history_rules(tmp_path, monkeypatch)


def test_the_tree_scan_reads_what_is_staged_not_the_working_copy(tmp_path, monkeypatch):
    g = git_repo(tmp_path)
    (tmp_path / "a.txt").write_text(SAMPLES["key-github"] + "\n", encoding="utf-8")
    g("add", ".")
    (tmp_path / "a.txt").write_text("clean\n", encoding="utf-8")
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    monkeypatch.setattr(ps, "APPROVED_IMAGES", tmp_path / "none")
    assert "key-github" in {f.rule for f in ps.scan_tree()}


@pytest.mark.parametrize("mode,rule", [("120000", "link-in-repository"), ("160000", "submodule")])
def test_links_and_submodules_are_reported(tmp_path, monkeypatch, mode, rule):
    g = git_repo(tmp_path)
    commit_text(g, tmp_path, "a.txt", "target\n")
    sha = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD" if mode == "160000" else "HEAD:a.txt"],
                         capture_output=True, text=True, check=True).stdout.strip()
    g("update-index", "--add", "--cacheinfo", f"{mode},{sha},entry")
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    monkeypatch.setattr(ps, "APPROVED_IMAGES", tmp_path / "none")
    assert rule in {f.rule for f in ps.scan_tree()}


def test_a_private_word_in_latin1_is_found():
    found = ps.scan_content("le café secret".encode("latin-1"), "a.txt", ["café"])
    assert {"not-utf8", "private-term"} <= {f.rule for f in found}


def test_an_escaped_address_in_json_is_found():
    data = ('{"contact": "someone' + "\\" + 'u0040example.org"}').encode()
    assert "email" in {f.rule for f in ps.scan_content(data, "a.json", suffix=".json")}


@pytest.mark.parametrize("text", ["api" + '_key = "violetlantern"', "pass" + "word: 'correcthorse'",
                                  "API" + "_KEY=violetlantern12", '"client' + '_secret": "plainwords"'])
def test_a_plain_word_in_a_credential_field_is_found(text):
    assert "secret-assigned" in rules(text), text


@pytest.mark.parametrize("text", ['api_key = "your-api-key"', "password = getpass.getpass()", "api_key = os.environ['X']",
                                  "token = load_token(path)", "password: <your password>"])
def test_a_credential_field_without_a_value_passes(text):
    assert "secret-assigned" not in rules(text), text


def test_a_private_word_cannot_hide_in_a_no_reply_address():
    text = f"Co-Authored-By: x <1+{CANARY}" + "@users.noreply.github.com>"
    assert "private-term" in {f.rule for f in ps.scan_message(text, "m", [CANARY])}


def icc(text):
    return b"\0" * 128 + text.encode("utf-16-be") + b"\0" * 16


def test_a_private_word_in_a_png_colour_profile_is_found():
    body = b"icc\0\0" + zlib.compress(icc(CANARY))
    assert "private-term" in {f.rule for f in ps.scan_image(with_chunk(b"iCCP", body), "a.png", [CANARY])}


def test_a_private_word_in_a_jpeg_colour_profile_is_found():
    data = jpeg_with(0xE2, b"ICC_PROFILE\0\x01\x01" + icc(CANARY))
    assert "private-term" in {f.rule for f in ps.scan_image(data, "a.jpg", [CANARY])}


def test_a_private_word_in_a_webp_colour_profile_is_found():
    assert "private-term" in {f.rule for f in ps.scan_image(webp_with(b"ICCP", icc(CANARY)), "a.webp", [CANARY])}


def test_a_private_word_in_compressed_png_text_is_found():
    body = b"Comment\0\0" + zlib.compress(CANARY.encode())
    assert "private-term" in {f.rule for f in ps.scan_image(with_chunk(b"zTXt", body), "a.png", [CANARY])}


def test_a_second_jpeg_after_the_first_is_found():
    jpg = cv2.imencode(".jpg", np.full((16, 16, 3), 120, np.uint8))[1].tobytes()
    assert "image-trailing-data" in {f.rule for f in ps.scan_image(jpg + jpg, "a.jpg")}


def test_a_jpeg_with_restart_markers_and_stuffing_is_read_whole():
    jpg = cv2.imencode(".jpg", np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8),
                       [cv2.IMWRITE_JPEG_RST_INTERVAL, 2])[1].tobytes()
    assert ps.scan_image(jpg, "a.jpg") == []


def test_a_truncated_webp_is_found():
    data = webp_with(b"EXIF", b"some")
    assert "image-damaged" in {f.rule for f in ps.scan_image(data[:-3], "a.webp")}


@pytest.mark.parametrize("text", ['<svg><style>a{fill:url(art.svg#b)}</style></svg>', '<svg><style>@import "x.css";</style></svg>'])
def test_external_references_in_svg_css_are_found(text):
    assert "svg-external" in {f.rule for f in ps.scan_svg(text, "a.svg")}


def test_svg_is_judged_by_content_not_by_name():
    data = b'<?xml version="1.0"?><svg><metadata>made by</metadata></svg>'
    assert "svg-editor-data" in {f.rule for f in ps.scan_content(data, "drawing.xml", suffix=".xml")}


def test_a_large_file_pointer_is_found():
    data = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 12\n"
    assert "lfs-pointer" in {f.rule for f in ps.scan_content(data, "a.bin")}


def test_compressed_metadata_cannot_fill_the_memory(monkeypatch):
    monkeypatch.setattr(ps, "MAX_INFLATED", 1024)
    body = b"Comment\0\0" + zlib.compress(b"x" * 10_000_000)
    assert "image-metadata" in {f.rule for f in ps.scan_image(with_chunk(b"zTXt", body), "a.png")}


def test_a_short_read_from_git_stops_the_scan():
    class Fake:
        stdin = io.BytesIO()
        stdout = io.BytesIO(b"abc blob 10\nshort\n")

        def wait(self):
            return 0
    store = ps.Objects()
    store.cat = Fake()
    with pytest.raises(ps.ScanError):
        store.read("abc")


def test_a_failed_git_stops_the_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "ROOT", tmp_path)                 # (not a repository)
    with pytest.raises(ps.ScanError):
        ps.git("rev-list", "--all")


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
    """A subject or a picture passed to someone else says nothing of where it was made, in any encoding."""
    d, marker = private_run
    needles = [marker.encode(e) for e in ("utf-8", "utf-16-le", "utf-16-be")]
    leaks = [p.name for p in d.rglob("*") if p.is_file() and any(n in p.read_bytes() for n in needles)]
    assert not leaks, leaks


def test_a_second_reader_finds_no_metadata_in_its_pictures(private_run):
    """Pillow, as an independent reader of what the scan's own parser says."""
    Image = pytest.importorskip("PIL.Image")
    d, _ = private_run
    for p in d.rglob("*"):
        if p.suffix.lower() in (".png", ".jpg"):
            with Image.open(p) as im:
                extra = set(im.info) - {"dpi", "jfif", "jfif_version", "jfif_unit", "jfif_density", "gamma", "srgb"}
                assert not extra and not im.getexif(), (p.name, extra)


@pytest.mark.skipif(not os.environ.get("REFINISH_OFFLINE"), reason="only inside CI's network namespace")
def test_the_kernel_has_really_removed_the_network():
    s = socket.socket()
    s.settimeout(3)
    with pytest.raises(OSError):
        s.connect(("1.1.1.1", 53))
    s.close()
