---
name: refinish
description: Re-finishes an existing character picture or background in another art style by code, never by regenerating it: the drawing stays, only the finish changes. 37 bundled styles: TV anime cel and its heavy, bold-ink, film, night, sunset, pastel, 90s variants; a cleaner de-AI finish; duotone, sepia, cyanotype, risograph; watercolour, gouache, thick paint; manga screentone, key drawing, screen print; ink wash, woodblock, pop art, neon, stained glass, paper cut, charcoal, pastel, stickers; pixel sprites; landscapes. Also matches the finish of reference pictures by measurement, tweaks a style from words ("softer shadows"), relights for night or sunset, mixes finishes by part, and composites figures into scenes. Use it whenever the user wants a picture in a technique's style, an anime look, a less AI-looking finish, a manga, watercolour, woodblock, pixel or retro version, a night version, consistent sprites or a figure in a scene, even if they only say "make this look hand-drawn" or "it looks too AI".
license: MIT
compatibility: Python 3.10+ with numpy, opencv-python and scipy (Pillow optional, for reading PNG notes). No image model, no network, no GPU.
metadata:
  version: "0.1.0"
---

# Refinish

Regenerating a picture to change its style also changes the character: another face, another hand, a costume that drifts. This skill keeps the drawing and paints a new finish over it, the way an anime finishing department or a print studio would: flat tones laid where the source drew its shadows, lines re-inked or re-traced, washes, screens, blocks, pixels. Everything is code. The result is the same character, frame for frame, in the new finish.

What it can and cannot do (tell the user before starting):
- **Can**: change the finish — how shadows are shaped and coloured, the lines' weight, colour and texture, the palette, the medium (paint, print, ink, pixels), the hour's light.
- **Cannot**: change the design — proportions, the way eyes are drawn, the pose, the number of folds. A request for "the style of X" gets X's finish on the user's own drawing, not a redrawing.

## Workflow

Copy this checklist and tick it off. Each step ends on its done-criterion.

- [ ] **0. Tools**: `python -c "import numpy, cv2, scipy"` succeeds.
- [ ] **1. Source**: `scripts/check_input.py` graded the picture; a figure is a cut-out (transparent background), or was cut out of its scene with `scripts/cutout.py`; below 2000 px tall it was enlarged with `scripts/prep.py`.
- [ ] **2. Subject**: a subject file whose parts are right on the parts sheet (`scripts/auto_parts.py`, with a hints file for the cel, paint and print styles), or `scripts/scene_subject.py` for a background.
- [ ] **3. Style**: chosen from [references/presets.md](references/presets.md) with the user, or written or measured (steps 7–8).
- [ ] **4. Finish**: `scripts/refinish.py` ran; its check has no FAIL left unexplained.
- [ ] **5. Look**: the result seen at full size, the face and hands at 1:1, beside the source.
- [ ] **6. Deliver**: the disclosure the user's platform needs, noted in the file if they want it.

### 1. Check the source

`python scripts/check_input.py PICTURE.png` grades a picture for each family of styles and says what to expect:

- An outline drawn on both sides of the figure: a closed outline is drawn where it is missing, but a rim light's colour stays in the fill.
- Flat shading: soft airbrushed gradients blotch under flat-tone styles.
- A cut-out: the figure styles need one.

The thresholds come from [references/input-check.md](references/input-check.md).

A figure on a transparent or plain background is the best source. A character drawn into a scene works too: draw a rough outline round the figure and `scripts/cutout.py` finds the exact edge by colour. It gives:
- the cut-out;
- the background with the figure's place filled.

Each can be finished on its own; the figure is then put back where it was with `scripts/composite.py`. Holes for the gaps the outline went round, bands, points, a trimap the person paints, what to change for each symptom, and the limits: [references/cutout.md](references/cutout.md).

If the user is about to generate the picture, the source spec in [references/source-spec.md](references/source-spec.md) is the best investment: measured on one character, the drawn outline went from 58% to 92% and the shading came out paintable. [references/presets.md](references/presets.md) gives each style's own pre-production advice.

### 2. Make the subject file

A subject file says what each part of the picture is (skin, hair, each garment) and where the eyes and mouth are. The styles paint each material from its own colour model, so a mislabelled region gets the wrong colour.

- **Figures**: run `python scripts/auto_parts.py IMAGE.png subject.json` for a draft, then look at its parts sheet (`subject.sheet.jpg`) and face sheet. For the cel, paint and print styles, write a hints file:
  - points on each material, from `scripts/hints.py pick`, which puts each point in the middle of its colour;
  - a rough box per part, generous round arms, forearms and thighs;
  - boxes round the eyes and the mouth.

  Then run `auto_parts.py --hints` again. Two rounds settle most pictures. When they do not, change the approach rather than the points: [subject-file.md](references/subject-file.md), "When the parts will not come right", lists what to try.
- **Backgrounds**: `python scripts/scene_subject.py IMAGE.png subject.json` finds the scene's areas by colour and guesses their kinds (sky, far hills, foliage, ground, ...). A painted background takes `deai-light` or a scene style, not a cel style: flat tones break its gradients into blotches (presets.md, Scenes).
- **No parts needed**: the de-AI and duotone styles run on the draft as it is.

Everything about subjects and hints, with the measured failure modes, is in [references/subject-file.md](references/subject-file.md). When a person reviews the parts, ask them for one sentence about what is wrong ("the bow is part of the skirt"), never for boxes or points; turn the sentence into hints yourself.

### 3. Choose a style

[references/presets.md](references/presets.md) lists all 37 styles by family. For each it gives:
- what the style needs (parts or not);
- the pre-production advice;
- its known limits.

Show the user two or three candidates on their own picture rather than describing them.

### 4. Re-finish

```bash
python scripts/refinish.py subject.json styles/tv-cel.json out.png
```

`--hour night|sunset|dusk|film-night` relights any style for another hour. The script prints JSON:
- the style and engine;
- what the same-material guard moved (pixels the part map put in the wrong part, given back to their material before painting);
- the check:
  - **cel and paint**: the result is checked against the source (parts, colours, outline, lost features);
  - **engines built on a cel finish** (print, woodblock, wash, pencil, pixel, tone and the special styles): that cel finish is checked;
  - **de-AI**: its own colour-shift check (H1);
  - **every engine, the duotones too**: its own result for a skin printed another colour (O7), a box round the features (O8) and mottled darks (O9).

Each FAIL names a box and a likely cause; [references/checks.md](references/checks.md) says how to fix each one, usually a hint point or a box.

### 5. Look before showing

The numbers catch the common mistakes, not all of them. Before showing a result, look at it at full size beside the source, and at the face and the hands at 1:1. Look for blotches in soft areas, a material in another's colour, and lost eye highlights. A style's limits are in presets.md; say them rather than hiding them.

When something is wrong, change a setting for this picture rather than a script. Change one at a time, a part's rule before the style, and compare before and after. [references/adjusting.md](references/adjusting.md) gives each common problem's cause and setting:
- a skin painted another colour;
- a box round the features;
- frayed shadow edges and flecks (`"deblotch"` per part, or `"auto_deblotch"`);
- mottled darks;
- an unreadable face;
- a lost thin part;
- a costume in the wrong ink.

Settle a setting for a batch on a few pictures, then check it on ones you did not tune it on.

### 6. Deliver

The finish does not change where a picture came from. A picture generated with an image model is still AI-generated after any style here, the de-AI styles included: they give a cleaner finish and are not tuned against any detector. [references/legal-and-disclosure.md](references/legal-and-disclosure.md) covers:
- style and copyright;
- what Steam and pixiv ask for.

`python scripts/png_note.py out.png "AI-assisted: ..."` writes a note into the PNG.

### 7. Adjust a style by words

```bash
python scripts/tweak_style.py tv-cel my-style.json "softer shadows, more vivid"
```

It moves each matched word's keys one step (`--steps N` for more) and names the measured number that should move. Words in English, Chinese and Japanese; `--list` shows them all. A word that names the design ("bigger eyes") has no entry: the finish cannot change the drawing.

### 8. Match reference pictures

```bash
python scripts/fit_style.py subject.json ref1.png ref2.png --out matched.json
```

It measures the references' finish, starts from the nearest bundled style and moves each number more than 10% off toward the references, round by round. [references/replicating-a-style.md](references/replicating-a-style.md) has the manual loop and the table of numbers to parameters.

Three rules hold either way:
- the reference pictures stay where the user keeps them, never copied into a project or a shared file;
- a style file holds numbers only;
- a style is named after its technique, never after the work or artist it was measured from.

### 9. Composite and camera

```bash
python scripts/composite.py scene.json frame.png
```

It lays re-finished figures over a background with a lens:
- depth of field and bokeh in linear light;
- light wrap;
- a grade of the background region by region (a night sky apart from the ground);
- bloom, vignette and grain.

`--raw` gives the plain paste-up to compare with. A depth of field inside one figure is the `focus` post layer. Details: [references/compositing.md](references/compositing.md).

### 10. Mix finishes, or finish only part of a picture

```bash
python scripts/recipe.py recipe.json out.png
```

A recipe lays finishes over a base, each limited to parts, kinds or areas (the face, the lines) and blended in:
- the clothes in watercolour, the face and hair in TV cel;
- a screentone multiplied over a watercolour;
- 30 % of the film everyday look over a heavy cel;
- only the hair cleaned of rendering noise, the rest as drawn.

Format, blend modes and examples: [references/recipes.md](references/recipes.md).

### 11. Repair the source

```bash
python scripts/repair.py image.png repaired.png --subject subject.json
```

It fixes a source's defects without restyling it: a cut-out's fringe, stray specks, gaps in the line art, colour that ran from one material into the next. Run it before a finish when the source has them, and look at its review picture. Details and limits: [references/repairs.md](references/repairs.md).

## Writing or changing a style

A style file is numbers only: shadows, lines, palette, touches, texture, the engine's own section and `post` layers (relight, paper, grain, halation, soften, curve, focus, and the scene layers). Start from the nearest bundled style and change one section at a time. Format and every key: [references/style-format.md](references/style-format.md).

## Scripts

All print JSON on stdout; exit code 0 means done, 1 done with doubts or failures to look at, 2 bad input.

| script | use |
|---|---|
| `cutout.py PICTURE.png OUTLINE.json OUT_DIR [--trimap T.png]` | cut a figure out of a picture with a background |
| `prep.py SRC.png OUT.png [--scale 2]` | crop to the figure and enlarge |
| `check_input.py PICTURE.png \| SUBJECT.json` | grade a source |
| `auto_parts.py IMAGE.png SUBJECT.json [--hints H.json]` | the subject file for a figure, with its parts sheet |
| `hints.py check \| points \| pick` | check hint points, turn region numbers into points, pick a point in a colour |
| `scene_subject.py IMAGE.png SUBJECT.json` | the subject file for a background |
| `parts.py SUBJECT.json` | rebuild and check a part map |
| `refinish.py SUBJECT.json STYLE.json OUT.png [--hour H]` | re-finish, with the guard and the checks |
| `check_output.py SUBJECT.json OUT.png` | check a result on its own |
| `measure_style.py ...` | measure a finish, compare two measurements |
| `fit_style.py SUBJECT.json REF.png ... --out STYLE.json` | fit a style to references |
| `tweak_style.py STYLE.json OUT.json "words"` | change a style by words |
| `composite.py SCENE.json OUT.png [--raw]` | composite and camera |
| `recipe.py RECIPE.json OUT.png` | mix finishes by part and blend mode |
| `repair.py PICTURE.png OUT.png [--fix ...] [--subject S.json]` | repair a source: fringe, specks, line gaps, bleed |
| `png_note.py OUT.png "text"` | a note in the PNG (any language) |
| `zoom.py PICTURE.png x0,y0,x1,y1 OUT.jpg` | an enlarged crop with a pixel grid, to read coordinates |

## Gotchas

- A figure under 2000 px tall loses its fine lines in the cel styles: `prep.py --scale 2` first, and pass `--upscaled 2` to `auto_parts.py`.
- Two materials of one colour (blue-grey hair over a pale blue cardigan, a beige coat on beige skin) are told apart only by boxes and lines. `auto_parts.py` says so in a doubt; look along that border first.
- A tall narrow box cuts off an arm or a thigh more often than any other mistake: box the whole limb.
- Night is not darkening: `--hour night` (a TV night colour model) and `--hour film-night` (a cinematic night grade) relight the colours. Generate the source in day colours under neutral light.
- On a console that is not UTF-8, the scripts print non-ASCII text escaped (still valid JSON).
