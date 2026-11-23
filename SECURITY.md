# Security

Refinish runs on your own machine. Its scripts read the pictures and JSON files they are given and write their results to the paths they are given. They open no network connection, download nothing, and never run code taken from a style, subject or recipe file.

- **Installing.** `scripts/check_env.py` changes nothing itself. The commands it prints install NumPy, SciPy and OpenCV from PyPI at pinned versions, each checked against the SHA-256 in `requirements.txt` or `requirements-headless.txt`, as prebuilt wheels only, so no package's build code runs on your machine.
- **The project's own checks.** CI actions are pinned by commit and hold read-only access. Every change goes through a scan of the files and the whole history for paths, addresses, keys and picture metadata (`tests/privacy_scan.py`).

## Reporting a vulnerability

If you find a way to make a script do something it should not, such as writing outside the paths it was given or running code from one of its input files, please report it privately: on this repository, open **Security**, then **Report a vulnerability**. Please don't open a public issue for it.

A fix goes into the next release, and the changelog says what was fixed.

Ordinary bugs, such as a wrong colour or a crash on an unusual picture, are welcome as [issues](https://github.com/owoevan-dev/refinish-skill/issues).
