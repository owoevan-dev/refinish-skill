#!/usr/bin/env python3
"""Writes skills/refinish/requirements.txt and requirements-headless.txt: the tested versions, each with the SHA-256 of
every wheel PyPI publishes for it, so pip installs only the files as they were published (its hash-checking mode).

To move a pin: change it below, run this, and let CI test the result.   python tests/update_pins.py"""
import json
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "refinish"
OPENCV = "5.0.0.93"
BY_PYTHON = {
    "numpy": (("2.2.6", 'python_version < "3.11"'), ("2.4.6", 'python_version == "3.11"'), ("2.5.5", 'python_version >= "3.12"')),
    "scipy": (("1.15.3", 'python_version < "3.11"'), ("1.17.1", 'python_version == "3.11"'), ("1.18.1", 'python_version >= "3.12"')),
}
HEADER = """# The versions Refinish is tested with, each with the SHA-256 of every wheel PyPI publishes for it, so pip installs
# only the files as they were published. scripts/check_env.py prints the install command for your machine.
#
# {which}
# Install one OpenCV package per environment: together they overwrite each other's cv2.
#
# OpenCV stays at 5.0 because the macOS wheels of 5.1 need macOS 15. NumPy and SciPy follow the Python version, since
# their newest releases have dropped the older ones. Written by tests/update_pins.py.
"""


def wheels(package, version):
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "python-client"}), timeout=60) as r:
        rows = json.load(r)["urls"]
    found = sorted({u["digests"]["sha256"] for u in rows if u["packagetype"] == "bdist_wheel" and not u.get("yanked")})
    if not found:
        raise SystemExit(f"{package} {version}: no wheels on PyPI")
    return found


def entry(package, version, marker):
    head = f"{package}=={version}" + (f"; {marker}" if marker else "")
    return " \\\n".join([head, *(f"    --hash=sha256:{h}" for h in wheels(package, version))]) + "\n"


def main():
    shared = "".join(entry(p, v, m) for p, rows in BY_PYTHON.items() for v, m in rows)
    for name, package, which in (
            ("requirements.txt", "opencv-python", "For a desktop. On a server or in a sandbox use requirements-headless.txt."),
            ("requirements-headless.txt", "opencv-python-headless", "For a server or a sandbox, with no graphics libraries.")):
        text = HEADER.format(which=which) + shared + entry(package, OPENCV, "")
        (SKILL / name).write_bytes(text.encode("utf-8"))
        print(name, text.count("--hash="), "hashes")


if __name__ == "__main__":
    main()
