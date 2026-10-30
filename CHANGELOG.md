# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - unreleased

### Added

- **Brand**: a light and a dark version of the logo, the README showing the one that suits the reader's theme; the logo and the social preview are English only.
- **Repository**: READMEs in English, 繁體中文, 简体中文, 日本語 and 한국어 with pictures of an original sample character in every finish; tests on GitHub Actions (Python 3.10 and 3.13); a contributing guide and issue forms (issues are open, outside pull requests are not).

- **Subjects**:
  - automatic parts for a figure (`auto_parts.py`): trapped-ball regions, the face and its eyes and mouth found in the skin, hint points and boxes grown by LazyBrush-style claiming, marker watershed and GrabCut, the box limit kept last;
  - doubts for boxes drawn too small, for two materials of one colour touching, for eye boxes used as given (glasses), and for one region holding two colours far apart (a gap in a line);
  - hint points cut a region where its lines fail: a part's own shading edge counts for little, and the line art goes with the fill nearest it;
  - hint tools (`hints.py check | points | pick`);
  - a colour-based subject for backgrounds (`scene_subject.py`) with guessed kinds, and advice on which styles suit a painted background (de-AI light; not the cel styles, which break its gradients into blotches); `check_input.py` tells a figure in a scene from a background on its own.
  - a cut-out from a picture with a background (`cutout.py`): a rough outline with holes for the gaps it goes round, GrabCut deciding the edge within a band, local keep and drop points, a painted trimap, small holes only filled, the edge's colour taken from inside; the background written with the figure's place filled, for finishing apart and putting the figure back; doubts where the colours either side of the cut are close or an area well inside the outline went to the background.
- **Engines**:
  - cel, paint, de-AI, duotone, pixel, manga tone, screen print, woodblock, wash (watercolour and ink) and pencil (an animator's key drawing);
  - a same-material guard run before every engine that paints by parts;
  - `deblotch`, a per-part rule for an airbrushed part whose shadow comes out in blotches.
- **Layers**:
  - relight (night, sunset, dusk, a cinematic night grade), paper, film grain, halation, lens softness, tone curve, depth of field inside a figure;
  - scene layers: a woodblock sky's bokashi, an ink painting's mist and distance, a watercolour's wet sky.
- **Checks** on every result:
  - parts, colours, outline and lost features against the source;
  - H1 for the de-AI engine;
  - the cel base for engines built on it.
- **Styles**: 37, named by technique, among them the special ones: Ben-Day pop art (two inks dotted side by side on one grid), neon sign (the lines as glowing tubes), stained glass (glazier's pieces in lead, the drawing painted on), paper cut (stacked sheets, no lines), charcoal and soft pastel on toned paper, and a die-cut sticker (the picture grows by its border).
- **Style tools**:
  - `fit_style.py` fits a style to reference pictures by measurement;
  - `tweak_style.py` changes one by plain words (English, Chinese, Japanese);
  - `measure_style.py` measures and compares finishes.
- **Recipes**: `recipe.py` mixes finishes by part, kind or area (the face, the lines) with paint-program blend modes and opacity.
- **Repairs**: `repair.py` fixes a source without restyling it: a cut-out's fringe, specks (dark dots only off a known face), line gaps (thinned, pruned, tips joined), colour run across a part's edge.
- **Compositing**: `composite.py`, a camera pass over figures and a background (depth of field and bokeh in linear light, light wrap, a region grade, bloom, grain).
- **Disclosure**: `png_note.py` writes a plain note into a PNG (tEXt, or iTXt for any language); a guide to style and copyright and to platform disclosure.
- **Look checks** O7 to O9 on every engine's own result, the duotones included: a skin printed another colour, a box round the features, mottled darks.
- **Adjusting guide** (`references/adjusting.md`): for each common problem, its cause, the setting that moves it, and how to check the change. The guide favours a setting chosen for the picture over a change to the scripts.
- `auto_deblotch` (off by default): the broader reading of the shading, only for parts whose own cut comes out ragged and whose two tones lie close.


### Known issues

All 37 finishes were run on 16 characters the code had never seen (10 with darker skin, 4 with soft airbrushed shading). 21 finishes passed every measure. These did not, and are not fixed yet:

- **Manga screentone** prints darker skin as paper or a light tone.
- **Pop art** leaves boxes round the eyes and the mouth.
- **The ukiyo-e print** lightens tan and olive skin nearly to paper. Deep brown skin is kept.
- **Soft airbrushed sources** break into ragged shadow edges under the flat-tone finishes. `check_input.py` warns on them.
- **duotone-auto** can break a dark face into specks.
- **When the face finder reads no eyes**, the hint boxes become whole rectangles of iris and mouth. A doubt says so; check the eye boxes on the face sheet.
- **The look checks miss most of these.** O7 flagged 1 of 57 skin failures, O8 8 of 15 box seams.

### Fixed

- Black shapes that overlap no longer merge into one, as crossed legs in black tights did.
  - The cel finishes laid every line at one darkness, which nearly vanishes on black cloth or hair. A line is now always darker than the paint beside it (`lines.own.gap`, 9), so the finishes built on a cel base, stained glass among them, see it too.
  - Manga screentone draws the lines inside solid black in white (ホワイト), as a manga artist does.
  - The woodblock styles leave a line inside a block printed nearly as dark as the sumi uncut (白抜き), so the paper shows along it.
  - Short flecks of fold stay dark in both; only lines of some length turn white.
- The woodblock styles printed every dark part in sumi, a navy skirt or brown shoes like black cloth. Dark cloth with a colour now prints in its own pigment at full strength (indigo, brown, red); hair keeps the prints' sumi, and anything darker than the sumi itself still takes it.
- A darker skin is no longer printed pale by the woodblock styles, nor left paper and broken into boxes by the manga screentone, nor turned to pale dots by the pop art.
- The features' boxes keep only the features: lightness counts half against the skin, and hair or cloth that runs into a box from outside is painted with its part.
- Engines that lay one colour per piece:
  - a skin-coloured run of an accessory's part, grown from a rough box, goes back to the skin;
  - a thin part's colour is read off its fill, not its outline.
- Dark areas no longer mottle into camouflage. The wash drift and the woodblock grain fade near solid; charcoal and pastel show only the tooth's grain; charcoal lays its darks flat and blends the skin.
- Paper cut keeps thin parts (a cord, a strap) and fills slivers with the cel's colour instead of white paper.
- Neon draws the face in paler, finer tubes instead of one glowing mass.
- Screen-print inks are the colours of the parts they print, not a mean of two neighbours.
- The paint styles keep a mass of pure black black.
