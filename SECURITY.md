# Security

Refinish runs on your own machine, with your rights. Its scripts read the pictures and JSON files they are given and write their results to the paths they are given. They open no network connection, download nothing, and never run code taken from a style, subject or recipe file. The one exception is the optional head parse (`seethrough_parse.py`), whose model loader fetches its weights from Hugging Face on first use and later asks whether they changed, if you installed those models. `HF_HUB_OFFLINE=1` stops that.

- **Input files are data.** Pictures, subjects, styles, recipes, scenes, hints, outlines and colour cards may come from someone else. JSON is parsed as data and checked field by field before anything is computed from it. A style's engine and a layer's operation come from fixed lists, so a file cannot name code to load. A picture of more than 100 million pixels is refused, and a PNG, JPEG or WebP claiming that is refused before it is decoded.
- **A subject, recipe or scene names the pictures it uses.** They are read, never written, and may be anywhere your account can read. A file from someone you don't trust could point at another picture of yours and show it in the result, so look at such a file before passing the result on.
- **Your originals are kept.** A result never replaces one of the files its run read, however the path is written, including through a link. Files are written beside their place and then moved in, so a crash or a full disk leaves the earlier file whole. `png_note.py` is the one tool that changes a picture you name, on purpose, and only its text note.
- **Other programs.** The scripts start none, except that `fit_style.py` runs `refinish.py` with the same Python, without a shell.
- **Installing.** `scripts/check_env.py` changes nothing itself. The commands it prints install NumPy, SciPy and OpenCV from PyPI at pinned versions, each checked against the SHA-256 in `requirements.txt` or `requirements-headless.txt`, as prebuilt wheels only, so no package's build code runs on your machine.
- **The project's own checks.** CI actions are pinned by commit and hold read-only access. Every change goes through a scan of the files and the whole history for paths, addresses, keys and picture metadata (`tests/privacy_scan.py`), and a second, independent scan by Gitleaks.

## Reporting a vulnerability

If you find a way to make a script do something it should not, such as writing outside the paths it was given or running code from one of its input files, please report it privately: on this repository, open **Security**, then **Report a vulnerability**. Please don't open a public issue for it.

A fix goes into the next release, and the changelog says what was fixed.

Ordinary bugs, such as a wrong colour or a crash on an unusual picture, are welcome as [issues](https://github.com/owoevan-dev/refinish-skill/issues).
