# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A Codex listing: the plugin's own manifest (`.codex-plugin/plugin.json`) and marketplace (`.agents/plugins/marketplace.json`) give the plugin page a name, icon, description, website, screenshots, starter prompts and the Creativity category; the skill carries its own name and icons (`agents/openai.yaml`).
- A display name, Refinish, in Claude's plugin manifest, for the plugin directory and `/plugin`.

### Changed

- Step 0 of SKILL.md installs `opencv-python-headless` on a server or in a sandbox, where `opencv-python` can fail to import for want of graphics libraries.

## [0.1.0] - 2026-10-30

### Added

- **Subjects**:
  - automatic parts for a figure (`auto_parts.py`): trapped-ball regions, the face and its eyes and mouth found in the skin, hint points and boxes grown by LazyBrush-style claiming, marker watershed and GrabCut, the box limit kept last;
  - doubts for boxes drawn too small, for two materials of one colour touching, for eye boxes used as given (glasses), and for one region holding two colours far apart (a gap in a line);
  - hint points cut a region where its lines fail: a part's own shading edge counts for little, and the line art goes with the fill nearest it;
  - hint tools (`hints.py check | points | pick`);
  - what to try when the parts will not come right after two rounds (`references/subject-file.md`): one sentence from the person, fewer and larger parts, one part for a dense pattern, tight eye boxes and an `eyes` part for a missed iris, finishing only the parts that are right, a finish that needs no parts, a source that can be split; the READMEs say so in their limits;
  - a colour-based subject for backgrounds (`scene_subject.py`) with guessed kinds, and advice on which styles suit a painted background (de-AI light; not the cel styles, which break its gradients into blotches); `check_input.py` tells a figure in a scene from a background on its own;
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
- **Delivery**: `prep.py --restore` puts a finish of the prepped picture back on the source's canvas, at the source's size and place.
- **Compositing**: `composite.py`, a camera pass over figures and a background (depth of field and bokeh in linear light, light wrap, a region grade, bloom, grain).
- **Disclosure**: `png_note.py` writes a plain note into a PNG (tEXt, or iTXt for any language); a guide to style and copyright and to platform disclosure, with a link to each source.
- **Look checks** O7 to O9 on every engine's own result, the duotones included: a skin printed another colour, a box round the features, mottled darks.
- **Adjusting guide** (`references/adjusting.md`): for each common problem, its cause, the setting that moves it, and how to check the change. The guide favours a setting chosen for the picture over a change to the scripts.
- `auto_deblotch` (off by default): the broader reading of the shading, only for parts whose own cut comes out ragged and whose two tones lie close.
- **Brand**: a light and a dark version of the logo, the README showing the one that suits the reader's theme; the logo and the social preview are English only; a plugin icon.
- **Repository**: READMEs in English, 繁體中文, 简体中文, 日本語 and 한국어 with pictures of an original sample character in every finish; tests on GitHub Actions (Python 3.10 and 3.13); a contributing guide, a security policy and issue forms (issues are open, outside pull requests are not); the licence also inside the skill's folder, which is often copied on its own.

### Known issues

All 37 finishes were run on 16 characters the code had never seen (10 with darker skin, 4 with soft airbrushed shading). 21 finishes passed every measure. These did not, and are not fixed yet:

- **Manga screentone** prints darker skin as paper or a light tone.
- **Pop art** leaves boxes round the eyes and the mouth.
- **The ukiyo-e print** lightens tan and olive skin nearly to paper. Deep brown skin is kept.
- **Soft airbrushed sources** break into ragged shadow edges under the flat-tone finishes. `check_input.py` warns on them.
- **duotone-auto** can break a dark face into specks.
- **When the face finder reads no eyes**, the hint boxes become whole rectangles of iris and mouth. A doubt says so; check the eye boxes on the face sheet.
- **A thin strand of hair across the face** can change colour halfway under the watercolour and stained-glass finishes: its narrow part is read as a line, its wider part as a fill. Hint points do not mend it.
- **One feature in two parts** (an iris given a part of its own by a hint) can print in two pigments under the woodblock styles.
- **Paper cut** can leave a thin light rim where two sheets meet (a collar against the hair, a ribbon).
- **The key drawing** can lay its coloured shadow guides as small filled patches along the edge of a dark part.
- **Closed and winking eyes** (^^, a wink) are not found by the face finder, and a dark object beside the face (a bottle held up) can be read as an eye: give the eye boxes by hand.
- **Spiral eyes** under the pastel finishes can show a faint ring where the protected box meets the repainted skin; **O2** reports eye whites painted as skin on eyes drawn with none ('><').
- **A hand round a dark, bubbly object** (a bottle of soda) can take dark specks on its fingers, and **small coloured marks** (a sparkle, an anger mark) can lose their colour.
- **`fit_style.py`** reads the references' colour figure-wide, so references with vivid costumes or backgrounds push a figure's colours too far, and a start style that boosts cloth by kind keeps doing so: start from the visually nearest style, and look at the result beside a reference.
- **The look checks miss most of these.** O7 flagged 1 of 57 skin failures, O8 8 of 15 box seams.

### Fixed

- Nothing fails in silence:
  - `composite.py` makes the output's folder, and stops with an error when a picture cannot be written instead of reporting a file it never wrote; every script writes its pictures that way.
  - `composite.py` lays a layer's own soft alpha as it is (a glow, a cast shadow, a half-opaque layer). Clearing an image model's faint halo is a choice per layer (`clear_halo`).
  - `--hour`, and a style's post layers, are refused for the pixel, sticker and neon finishes, which change the picture's size, instead of being skipped.
  - 16-bit pictures are read at their own depth instead of coming out white.
  - `refinish.py` and `recipe.py` exit 1 when a check FAILs, as SKILL.md says. `check_output.py` and `recipe.py` run the look checks O7 to O9 too, the duotones in a recipe included. `check_output.py --style` guards the part map as refinish.py does and runs that engine's checks; a file with layers over its finish (a style's post layers, or `--hour`) gets the part map's checks only, instead of having its layers misread as mistakes.
- The ink-wash mist was blended twice over. It is laid once, on the curve the two blends made, so the scenes look as they did by day; a night sky is no longer misted along its edges.
- The checks guide no longer says that every real defect is caught: the nine known mistakes are, and new pictures show the checks' limits.
- Stained glass paints the eyes on the glass as it paints the skin, and two painted parts meet on one piece. The white of an eye close to the skin's colour, which the protected boxes can miss, no longer has flecks of lead in it.
- The colour a file keeps under full transparency is read as black, so it no longer reaches the figure's visible edge through a blur: two files that differed only there once gave film-everyday-cel results 58,934 visible pixels apart.
- A recipe's layer paints only where it has paint: where a layer is transparent (a paper cut's trimmed edge) the base shows, and a half-transparent layer counts half.
- A `--palette-from` picture that cannot be read stops the run with exit 2 instead of being skipped; a style without a paint palette refuses the option.
- `repair.py`'s bleed fix splits a part's two tones at Otsu's threshold. A flat part (whose empty darker half was a NaN) and a part whose shade sat at the median both work now, and the colour run in is repainted.
- Bad input stops with exit 2 and a message instead of a traceback: a subject, style or recipe file that is not a JSON object, `--steps 0`, a pixel style with fewer than 8 colours, a crop box that holds nothing, `zoom.py --step 0`, a de-AI finish without a region map, a part map's cache whose region map is gone (it was once used as if nothing had changed). Reports written into a missing folder make it; a figure under 200 px tall no longer crashes the paint styles; a check no longer takes the mean of nothing; a sliver of skin colour is not read as a face. `auto_parts.py` lists only the review sheets it wrote.
- A layer's grade in `composite.py` reaches all of it, a half-clear veil or glow too (below half alpha it once kept its colour). Every blur is laid before the frame is cut, so what lies just outside the frame (a shoulder, a lamp, the background beyond a zoom's window) spreads into it.
- `repair.py` lays no line stroke in a protected box, and takes a dark dot for a speck only off a face the subject names in its focal ellipses, wherever that ellipse is whatever its detail weight: without one, or with a weak one, a mole on a face was once taken.
- `png_note.py` replaces a note of the same key in a compressed zTXt chunk too; other readers once still found the old note.
- A paint finish follows its own seed whatever ran before it: an earlier finish in a recipe once changed its palette.
- `tweak_style.py --steps N` reports each key from before the first step to after the last, not the last step alone.
- `fit_style.py` fits the cel finishes only, as it now says, and refuses a start in another technique; the READMEs say what a reference cannot pass on (the design, the scene's light).
- Black shapes that overlap no longer merge into one, as crossed legs in black tights did.
  - The cel finishes laid every line at one darkness, which nearly vanishes on black cloth or hair. A line is now always darker than the paint beside it (`lines.own.gap`, 9), so the finishes built on a cel base, stained glass among them, see it too.
  - Manga screentone draws the lines inside solid black in white (ホワイト), as a manga artist does.
  - The woodblock styles leave a line inside a block printed nearly as dark as the sumi uncut (白抜き), so the paper shows along it.
  - Short flecks of fold stay dark in both; only lines of some length turn white.
- The woodblock styles printed every dark part in sumi, a navy skirt or brown shoes like black cloth. Dark cloth with a colour now prints in its own pigment at full strength (indigo, brown, red); hair keeps the prints' sumi, and anything darker than the sumi itself still takes it.
- The woodblock styles no longer print deep brown skin pale. Tan and olive skin under them, and darker skin under the screentone, are still open (above).
- The features' boxes keep only the features: lightness counts half against the skin, and hair or cloth that runs into a box from outside is painted with its part.
- Engines that lay one colour per piece:
  - a skin-coloured run of an accessory's part, grown from a rough box, goes back to the skin;
  - a thin part's colour is read off its fill, not its outline.
- Dark areas no longer mottle into camouflage. The wash drift and the woodblock grain fade near solid; charcoal and pastel show only the tooth's grain; charcoal lays its darks flat and blends the skin.
- Paper cut keeps thin parts (a cord, a strap) and fills slivers with the cel's colour instead of white paper. What its outer edge's curve closes beyond the drawing (the gaps between loose strands of hair) is cut from the sheet beside it; it once showed the colour hidden there, in black slivers. The eyes lie on the face's paper as drawn, with no sheet of their own whose shadow made a dark ring round them, the white of an eye close to the skin's colour kept white, and a strand of the fringe beside an eye is paper like the rest of the fringe instead of a faint pasted piece.
- Neon draws the face in paler, finer tubes instead of one glowing mass.
- Screen-print inks are the colours of the parts they print, not a mean of two neighbours.
- The paint styles keep a mass of pure black black.

[Unreleased]: https://github.com/owoevan-dev/refinish-skill/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/owoevan-dev/refinish-skill/releases/tag/v0.1.0
