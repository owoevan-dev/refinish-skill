# Contributing

Thanks for wanting to help. Refinish is maintained by one person and has a fairly fixed direction, so here is how help works best.

## Issues are welcome

- **A picture that came out wrong.** Say which style you used, paste the command and the JSON it printed, and say what you expected. Attach the source and the result, or crops of the problem. Only attach pictures you have the right to share.
- **A finish you would like.** Name the technique (risograph, paper cutting, 1980s cel...) and describe what makes it that technique. Link reference pictures rather than uploading pictures you did not make.
- **Docs that left you stuck.** Quote the sentence and say what you tried.

Write in whatever language is easiest for you.

## Pull requests

Pull requests from outside the project are closed for now; only collaborators can open them. If you have a fix, describe it in an issue, or paste the patch there. When an idea or a patch from an issue is used, the changelog says whose it was. By posting a patch you agree that it may be used under the project's MIT licence.

## What the project will not take

- Styles named after a living artist, a studio or a title. Styles are named after their technique.
- Reference pictures, textures or brush strokes taken from someone else's work. Style files hold numbers only.
- Anything meant to get past AI-image detectors or to hide where a picture came from.
- An image model inside the skill. Refinish works on pictures you already have.

## Running the tests

```bash
python -m pip install --only-binary :all: --require-hashes -r skills/refinish/requirements-headless.txt
python -m pip install --only-binary :all: -r tests/requirements-dev.txt
python -m pytest -q tests
```

They take a few minutes. CI runs them on Linux, macOS and Windows, on every supported Python, and at both ends of the OpenCV range the skill supports. It also installs the skill from nothing the way a new user would (`tests/smoke_install.py`), and runs the workflow with the network removed.

## Privacy

`python tests/privacy_scan.py --history` looks through the files and the whole history for paths, addresses, keys, picture metadata and other things that should not be published. CI runs it too, and its report never prints what it found. Add `--show-paths` in your own terminal to see where. A new picture also needs its hash in `tests/public_images.sha256`, added after someone has looked at it.
