"""Shared fixtures: the scripts folder on the import path, and a small drawn figure made by code (no picture files
ship with the tests)."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "refinish"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cv2  # noqa: E402

from figures import draw_figure  # noqa: E402,F401


@pytest.fixture(autouse=True)
def no_inputs_from_another_test():
    """What counts as a run's input is per process; here one process runs many tests."""
    import _files
    _files._inputs.clear()


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
