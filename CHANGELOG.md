# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - unreleased

### Added

- **Subjects**:
  - automatic parts for a figure (`auto_parts.py`): trapped-ball regions, the face and its eyes and mouth found in the skin, hint points and boxes grown by LazyBrush-style claiming, marker watershed and GrabCut, the box limit kept last;
  - doubts for boxes drawn too small, for two materials of one colour touching, for eye boxes used as given (glasses), and for one region holding two colours far apart (a gap in a line);
  - hint points cut a region where its lines fail: a part's own shading edge counts for little, and the line art goes with the fill nearest it;
  - hint tools (`hints.py check | points | pick`);
  - a colour-based subject for backgrounds (`scene_subject.py`) with guessed kinds.
  - a cut-out from a picture with a background (`cutout.py`): a rough outline with holes for the gaps it goes round, GrabCut deciding the edge within a band, local keep and drop points, a painted trimap, small holes only filled, the edge's colour taken from inside; the background written with the figure's place filled, for finishing apart and putting the figure back; doubts where the colours either side of the cut are close or an area well inside the outline went to the background.
- **Engines**:
  - cel, paint, de-AI, duotone, pixel, manga tone, screen print, woodblock, wash (watercolour and ink) and pencil (an animator's key drawing);
  - a same-material guard run before every engine that paints by parts;
  - `deblotch`, a per-part rule for an airbrushed part whose shadow comes out in blotches.
- **Layers**:
  - relight (night, sunset, dusk, a film's night grade), paper, film grain, halation, lens softness, tone curve, depth of field inside a figure;
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

### Fixed

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
