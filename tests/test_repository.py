"""The repository as it is published: versions, links, install pins, the CI workflow, and what a file may contain."""
import ast
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from conftest import ROOT, SCRIPTS, SKILL
from privacy_scan import tracked_files

SKILLS = sorted(p.parent for p in (ROOT / "skills").glob("*/SKILL.md"))
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
REQUIREMENTS = SKILL / "requirements.txt"
HEADLESS = SKILL / "requirements-headless.txt"
PINNED_PYTHONS = ("3.10", "3.11", "3.12", "3.13", "3.14")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def repository_files():
    return [ROOT / f for f in tracked_files() if (ROOT / f).is_file()]


def frontmatter(skill):
    yaml = pytest.importorskip("yaml")
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    return yaml.safe_load(re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1))


# ----------------------------------------------------------------------------------------------------------- versions

def test_every_version_agrees():
    """The two manifests, both skills and the newest release in the changelog name one version."""
    claude, codex = load(ROOT / ".claude-plugin" / "plugin.json"), load(ROOT / ".codex-plugin" / "plugin.json")
    versions = {claude["version"], codex["version"], *(frontmatter(s)["metadata"]["version"] for s in SKILLS)}
    log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versions.add(re.search(r"^## \[(\d+\.\d+\.\d+)\]", log, re.M).group(1))
    assert len(versions) == 1, versions


def test_both_marketplaces_list_the_plugin():
    claude = load(ROOT / ".claude-plugin" / "plugin.json")
    markets = load(ROOT / ".claude-plugin" / "marketplace.json"), load(ROOT / ".agents" / "plugins" / "marketplace.json")
    assert all([p["name"] for p in m["plugins"]] == [claude["name"]] for m in markets)


def test_listing_icons():
    """Every icon a listing names is square and at least 48 px; Claude's directory wants 512 to 2048 px, under 2 MB."""
    cv2 = pytest.importorskip("cv2")
    claude, codex = load(ROOT / ".claude-plugin" / "plugin.json"), load(ROOT / ".codex-plugin" / "plugin.json")
    icon = ROOT / claude["icon"]
    h, w = cv2.imread(str(icon), cv2.IMREAD_UNCHANGED).shape[:2]
    assert w == h and 512 <= w <= 2048 and icon.stat().st_size < 2_000_000
    assert all((ROOT / rel).is_file() for rel in (codex["interface"]["composerIcon"], codex["interface"]["logo"],
                                                  *codex["interface"].get("screenshots", [])))


# -------------------------------------------------------------------------------------------------------------- links

def markdown_files():
    return [p for p in repository_files() if p.suffix == ".md"]


def test_markdown_links_resolve():
    """Markdown links and the HTML images and links in the READMEs' headers point at files that exist."""
    bad = []
    for md in markdown_files():
        text = re.sub(r"```.*?```", "", md.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"\]\(([^)#\s]+)", text) + re.findall(r"(?:src|srcset|href)=\"([^\"#]+)\"", text):
            if not re.match(r"[a-z]+:", target) and not (md.parent / target).exists():
                bad.append(f"{md.relative_to(ROOT)} -> {target}")
    assert not bad, bad


def heading_anchor(heading):
    """GitHub's anchor for a heading: inline code kept as text, tags and link markup dropped, lower case, punctuation
    other than hyphens and underscores removed, spaces to hyphens."""
    parts = re.split(r"(`[^`]+`)", heading.strip())
    text = "".join(p[1:-1] if p.startswith("`") else re.sub(r"</?[A-Za-z][A-Za-z0-9-]*(\s[^<>]*)?/?>", "", p)
                   for p in parts)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(path):
    seen, found, code = {}, set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        code = code ^ line.startswith("```")
        if not code and re.match(r"#{1,6} ", line):
            a = heading_anchor(line.lstrip("#"))
            found.add(a if a not in seen else f"{a}-{seen[a]}")
            seen[a] = seen.get(a, 0) + 1
    return found


def test_markdown_section_links_resolve():
    bad = []
    for md in markdown_files():
        for target, anchor in re.findall(r"\]\(([^)#\s]*)#([^)\s]+)\)", md.read_text(encoding="utf-8")):
            dest = md.parent / target if target else md
            if not re.match(r"[a-z]+:", target) and dest.suffix == ".md" and anchor not in anchors(dest):
                bad.append(f"{md.relative_to(ROOT)} -> {target}#{anchor}")
    assert not bad, bad


def test_readmes_offer_every_language():
    readmes = sorted(p.name for p in ROOT.glob("README*.md"))
    assert len(readmes) == 5, readmes
    for name in readmes:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert all(other in text for other in readmes if other != name), name


# ------------------------------------------------------------------------------------------------------ what files hold

def test_no_hidden_characters():
    """No text file holds a character that does not show: bidirectional controls, zero-width characters, a byte order
    mark, other format or control characters. A viewer may reorder the text round them (Trojan Source, CVE-2021-42574)."""
    hits = []
    for p in repository_files():
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            bad = sorted({f"U+{ord(c):04X}" for c in line.removesuffix("\r")
                          if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp", "Co", "Cs") and c != "\t"})
            if bad:
                hits.append(f"{p.relative_to(ROOT)}:{i}: {', '.join(bad)}")
    assert not hits, "\n".join(hits[:40])


def test_files_fit_the_plugin_directory():
    """The repository root is the plugin folder: every file under 5 MiB, and nothing binary but images."""
    for p in repository_files():
        assert p.stat().st_size < 5 * 2 ** 20, f"{p.relative_to(ROOT)} is 5 MiB or larger"
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            assert b"\0" not in p.read_bytes(), f"{p.relative_to(ROOT)} is a binary file"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_a_skill_ships_only_what_it_should(skill):
    """What an installed skill holds: its documents, scripts, style numbers, drawn eval pictures and icons."""
    allowed = {".md", ".py", ".json", ".yaml", ".txt", ".png", ".svg", ".sh", ""}
    for f in tracked_files():
        p = ROOT / f
        if skill in p.parents:
            assert p.suffix.lower() in allowed, f
            assert p.suffix or p.name == "LICENSE", f


# ------------------------------------------------------------------------------------------------------- install pins

def entries(path):
    """A requirements file as (package, version, marker, hashes), its continued lines joined."""
    rows, current = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        current.append(line.rstrip("\\").strip())
        if not line.endswith("\\"):
            spec, _, rest = current[0].partition(";")
            name, version = spec.strip().split("==")
            hashes = [c.removeprefix("--hash=sha256:") for c in current[1:]]
            rows.append((name, version, rest.strip(), hashes))
            current = []
    assert not current, path
    return rows


def pins(path=None):
    rows = {}
    for name, version, marker, _ in entries(path or REQUIREMENTS):
        rows.setdefault(name, []).append((version, marker))
    return rows


def applies(marker, python):
    if not marker:
        return True
    op, value = re.fullmatch(r'python_version\s*(<|==|>=)\s*"(\d+\.\d+)"', marker).groups()
    a, b = (tuple(map(int, v.split("."))) for v in (python, value))
    return {"<": a < b, "==": a == b, ">=": a >= b}[op]


@pytest.mark.parametrize("path,opencv", [(REQUIREMENTS, "opencv-python"), (HEADLESS, "opencv-python-headless")],
                         ids=["desktop", "headless"])
@pytest.mark.parametrize("python", PINNED_PYTHONS)
def test_requirements_pin_each_package_once_per_python(path, opencv, python):
    rows = pins(path)
    assert set(rows) == {"numpy", "scipy", opencv}
    assert all(sum(applies(m, python) for _, m in rows[name]) == 1 for name in rows)


@pytest.mark.parametrize("path", [REQUIREMENTS, HEADLESS], ids=["desktop", "headless"])
def test_requirements_pin_every_wheel_by_hash(path):
    """Hash-checking mode: pip installs a package only as PyPI published it."""
    for name, version, _, hashes in entries(path):
        assert re.fullmatch(r"\d+(\.\d+)+", version), name
        assert len(hashes) >= 5 and len(set(hashes)) == len(hashes), (name, version)
        assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes), (name, version)


def test_both_requirements_differ_only_in_the_opencv_package():
    a, b = entries(REQUIREMENTS), entries(HEADLESS)
    assert [r for r in a if r[0] in ("numpy", "scipy")] == [r for r in b if r[0] in ("numpy", "scipy")]
    assert pins(REQUIREMENTS)["opencv-python"] == pins(HEADLESS)["opencv-python-headless"]


def test_pins_are_inside_the_tested_range():
    import check_env
    for name, key in (("numpy", "numpy"), ("scipy", "scipy"), ("opencv-python", "cv2")):
        assert all(check_env.in_range(key, v) for v, _ in pins()[name]), name


def test_oldest_constraints_sit_at_the_floor():
    import check_env
    rows = dict(l.split("==") for l in (ROOT / "tests" / "constraints-oldest.txt").read_text(encoding="utf-8").split("\n")
                if l and not l.startswith("#"))
    assert check_env.version_tuple(rows["opencv-python-headless"]) == check_env.TESTED["cv2"][0]
    assert check_env.version_tuple(rows["scipy"]) == check_env.TESTED["scipy"][0]
    assert check_env.in_range("numpy", rows["numpy"])


def test_script_headers_allow_the_pin():
    """`uv run` reads the header of a script: it must resolve to the version the constraints pin."""
    pin = pins()["opencv-python"][0][0]
    pin_t = tuple(int(v) for v in pin.split(".")[:2])
    seen = 0
    for p in SCRIPTS.glob("*.py"):
        head = re.search(r"^# dependencies = (\[.*\])$", p.read_text(encoding="utf-8"), re.M)
        if not head:
            continue
        for dep in json.loads(head.group(1)):
            if dep.startswith("opencv"):
                seen += 1
                low, high = re.fullmatch(r"opencv-python>=([\d.]+),<([\d.]+)", dep).groups()
                assert tuple(map(int, low.split("."))) <= pin_t < tuple(map(int, high.split("."))), p.name
    assert seen >= 15


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_step_zero_uses_the_environment_check(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "check_env.py" in text and "pip install numpy" not in text


# --------------------------------------------------------------------------------------------------- the environment

def fake_env(monkeypatch, versions, errors=None, dists=None, managed=False):
    import check_env
    monkeypatch.setattr(check_env, "try_imports", lambda: (dict(versions), dict(errors or {})))
    monkeypatch.setattr(check_env, "installed_opencv", lambda: dict(dists or {}))
    monkeypatch.setattr(check_env, "_is_installed", lambda n: n in versions)
    monkeypatch.setattr(check_env, "externally_managed", lambda: managed)
    return check_env


GOOD = {"numpy": "2.5.5", "scipy": "1.18.1", "cv2": "5.0.0"}
GONE = {n: "ModuleNotFoundError: no" for n in GOOD}


def test_env_ok(monkeypatch, tmp_path):
    env = fake_env(monkeypatch, GOOD, dists={"opencv-python": "5.0.0.93"})
    assert env.report(tmp_path / "v") == (env.report(tmp_path / "v")[0], 0)
    assert env.report(tmp_path / "v")[0]["status"] == "ok"


def test_env_nothing_installed_goes_into_this_python(monkeypatch, tmp_path):
    env = fake_env(monkeypatch, {}, GONE)
    out, code = env.report(tmp_path / "v")
    assert code == 2 and out["status"] == "install" and len(out["argv"]) == 1 and out["use_python"] == sys.executable
    assert "--require-hashes" in out["argv"][0] and ":all:" in out["argv"][0]
    assert any(a.endswith("requirements.txt") or a.endswith("requirements-headless.txt") for a in out["argv"][0])


def test_env_some_installed_gets_its_own_environment(monkeypatch, tmp_path):
    """Pins applied over an existing numpy would change it under the user's other projects."""
    env = fake_env(monkeypatch, {"numpy": "2.3.1"}, {k: v for k, v in GONE.items() if k != "numpy"})
    out, code = env.report(tmp_path / "v")
    assert code == 2 and len(out["argv"]) == 2 and out["argv"][0][1:3] == ["-m", "venv"]
    assert out["use_python"].startswith(str(tmp_path))


def test_env_two_opencv_packages_get_their_own_environment(monkeypatch, tmp_path):
    env = fake_env(monkeypatch, GOOD, dists={"opencv-python": "5.0.0.93", "opencv-python-headless": "5.0.0.93"})
    out, code = env.report(tmp_path / "v")
    assert code == 2 and out["status"] == "install" and out["argv"][0][1:3] == ["-m", "venv"]
    assert str(env.REQUIREMENTS[True]) in out["argv"][-1]


def test_env_outside_the_tested_range_still_runs(monkeypatch, tmp_path):
    env = fake_env(monkeypatch, {**GOOD, "cv2": "4.8.1"}, dists={"opencv-python": "4.8.1.78"})
    out, code = env.report(tmp_path / "v")
    assert code == 1 and out["status"] == "untested" and out["outside_tested_range"] == ["cv2"]


def test_env_system_managed_python_gets_its_own_environment(monkeypatch, tmp_path):
    env = fake_env(monkeypatch, {}, GONE, managed=True)
    assert env.report(tmp_path / "v")[0]["argv"][0][1:3] == ["-m", "venv"]


def test_env_broken_desktop_opencv_suggests_headless(monkeypatch, tmp_path):
    errors = {"cv2": "ImportError: libGL.so.1: cannot open shared object file"}
    env = fake_env(monkeypatch, {k: v for k, v in GOOD.items() if k != "cv2"}, errors, dists={"opencv-python": "5.0.0.93"})
    assert str(env.REQUIREMENTS[True]) in env.report(tmp_path / "v")[0]["argv"][-1]


def test_env_old_python(monkeypatch, tmp_path):
    import check_env
    monkeypatch.setattr(check_env, "MIN_PYTHON", (99, 0))
    out, code = check_env.report(tmp_path / "v")
    assert code == 2 and out["status"] == "python-too-old"


def test_env_script_changes_nothing(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_env.py")], cwd=tmp_path, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode in (0, 1), r.stderr[-500:]
    assert json.loads(r.stdout)["status"] in ("ok", "untested") and not list(tmp_path.iterdir())


def test_env_runs_with_the_standard_library_alone():
    tree = ast.parse((SCRIPTS / "check_env.py").read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)


# --------------------------------------------------------------------------------------------------------- the workflow

def workflow():
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    d["on"] = d.get("on", d.get(True))                  # (YAML 1.1 reads the key `on` as true)
    return d


def test_workflow_reads_only():
    assert workflow()["permissions"] == {"contents": "read"}
    assert not any("permissions" in j for j in workflow()["jobs"].values())


def test_workflow_runs_no_untrusted_trigger():
    assert set(workflow()["on"]) == {"push", "pull_request", "schedule", "workflow_dispatch"}
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target" not in text and "workflow_run" not in text and "secrets." not in text


def test_workflow_pins_every_action_by_commit():
    for name, job in workflow()["jobs"].items():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), (name, step["uses"])


def test_workflow_keeps_no_credentials():
    for name, job in workflow()["jobs"].items():
        for step in job["steps"]:
            if "actions/checkout" in step.get("uses", ""):
                assert step["with"]["persist-credentials"] is False, name


def test_workflow_jobs_have_time_limits():
    assert all("timeout-minutes" in j for j in workflow()["jobs"].values())


def test_workflow_gate_needs_every_required_job():
    jobs = workflow()["jobs"]
    assert set(jobs["gate"]["needs"]) == {"tests", "oldest", "install", "privacy"}
    assert "always()" in jobs["gate"]["if"]
    assert jobs["latest"]["continue-on-error"] is True and jobs["report"]["continue-on-error"] is True


def test_workflow_covers_every_supported_python_and_system():
    rows = workflow()["jobs"]["tests"]["strategy"]["matrix"]["include"]
    assert {r["python-version"] for r in rows} == set(PINNED_PYTHONS)
    assert {r["os"].split("-")[0] for r in rows} == {"ubuntu", "macos", "windows"}
    assert {r["opencv"] for r in rows} == {"desktop", "headless"}
    assert all(r["requirements"] == ("requirements.txt" if r["opencv"] == "desktop" else "requirements-headless.txt")
               for r in rows)


def test_workflow_verifies_what_it_downloads():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"GITLEAKS_SHA256: [0-9a-f]{64}", text) and "sha256sum --check" in text
    assert "--redact" in text
