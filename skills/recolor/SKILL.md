---
name: recolor
description: "Recolours an existing character picture to a colour card by code, never by regenerating it: the drawing, the shapes of its shadows and its lines stay, and each part takes the card's colours in a clean anime cel finish. A card names colours per part, per kind (all hair, all metal) or by role (main, sub, accent colour), and its bases are enough: each part's shadow, second shadow and highlight are derived the way colour designers turn shadows (cooler for most materials, warmer for skin, a tint for whites). The lines follow the new colours, the irises are recoloured inside the protected face, and every result is checked against the card. Use it whenever the user wants a character in other colours: an alternate colour scheme or outfit colour, a palette swap, team or faction colours, a recolour to a colour card or a swatch picture, a dazzling multicolour scheme, or 'what would she look like with silver hair', even if they never say 'recolour'."
license: MIT
compatibility: Python 3.10+ with numpy, opencv-python and scipy. Runs the Refinish skill's scripts, which ship beside it in the same plugin. No image model, no network, no GPU. Two optional segmentation models (See-Through, SAM 2), installed apart and best on an NVIDIA GPU, can read the head and split the eyes (../refinish/references/seethrough.md).
metadata:
  author: "owoevan-dev"
  version: "0.2.0"
---

# Recolor

Asking an image model for "the same character in blue" redraws the character: another face, another costume. This skill keeps the picture and changes only its colours, the way an anime colour designer (色彩設計) gives each material a base, a shadow, a second shadow and a highlight, and the finishing department paints them where the drawing put its tones. Everything is code: the result is the same drawing, line for line, in the card's colours.

The scripts are the Refinish skill's, in `../refinish/scripts/` beside this folder (the two skills ship together). Commands below are run from this skill's folder; from anywhere else, give the scripts' full path.

What it can and cannot do (tell the user before starting):
- **Can**: give any part its own colours: the hair, the irises, each garment, the accessories; from colours the user names, from a colour card picture, or from a scheme by kind and role. Shadows and highlights the card leaves out are derived. The lines take the new colours; the eyes, lashes and mouth stay as drawn.
- **Cannot**: colour a black-and-white drawing (the parts are read from its colours); move the shadows (they stay where the source drew them); keep a pattern's own several colours inside one part (a patterned garment comes out tone on tone in its card colour); repaint what the part map got wrong (a collar labelled as the headphones takes the headphones' colour).

## Workflow

Copy this checklist and tick it off. Each step ends on its done-criterion.

- [ ] **0. Tools**: `python -c "import numpy, cv2, scipy"` succeeds. If it does not: `python -m pip install numpy scipy opencv-python`; on a server or in a sandbox, `opencv-python-headless` instead. `../refinish/scripts/palette.py` exists: Recolor runs the Refinish skill's scripts, so the two skills are installed side by side.
- [ ] **1. Subject**: a subject file whose parts are right, every part the card will change holding only its own material.
- [ ] **2. Card**: a colour card the user approved on its board.
- [ ] **3. Apply**: `palette.py apply` wrote the carded subject; every part the user named is in its report.
- [ ] **4. Finish**: `refinish.py` ran a cel style on the carded subject; no RC finding left unexplained.
- [ ] **5. Look**: the result at full size beside the source, the face at 1:1, and every box RC5 names.
- [ ] **6. Touch** (when the look finds a patch in the wrong colour): `touch.json` written, its preview looked at, the result finished and looked at again.

### 1. The subject

Make the subject file as the Refinish skill does: its steps 1 and 2 ([../refinish/SKILL.md](../refinish/SKILL.md)): a cut-out figure, enlarged below 2000 px, and parts from `auto_parts.py` with a hints file.

The eyes are where a recolour goes wrong most: a pale iris read as the white, a dark one as the lashes. When See-Through and SAM 2 are installed, read the head with them first (`seethrough_parse.py`, then `auto_parts.py --parse`: [seethrough.md](../refinish/references/seethrough.md)). Each eye is split into its iris, its white and its lashes; the iris becomes the part `irises`, which a card colours whole, and the white and the lashes stay as drawn. Look at every eye on the parse's sheet (`parse.eyes.jpg`) and click the ones split wrong before making the subject: a click there fixes the eye at its source, where a touch (step 6) only patches the result.

Recolouring shows every mistake of the part map that a finish in the same colours hides, so look harder at the parts sheet (`subject.sheet.jpg`) than for a restyle:
- **Each part the card changes holds one material.** A strip of collar inside the headphones' part turns the headphones' colour; a nail labelled as the cardigan turns the cardigan's.
- **The irises are a part of kind `eyes`**, and the whites of the eyes are not part of a garment. An eye whose iris is labelled hair is left as drawn (check RC3 says so). Keep the brows out of the iris part: a thin lash line or strand joined to an iris stays as drawn, but a brow as thick as the iris takes the iris's new colour.
- **Solid black (spot blacks, an inked style's masses) is a part of its own**, kind `accessory`: roles pass it by.
- **Something the character holds is a prop.** Give a brush, a cup, a sword or a bag a part of its own with `"prop": true` in the hints. A scheme by kinds and roles then leaves it as drawn, and the card can still name it. Without the flag the roles treat it as clothing: under a vivid card, a painter's brush came out teal.

### 2. The card

A card is a small JSON file in the format `refinish-palette/1`. The format, every field and what a card can say: [references/palette-format.md](references/palette-format.md). How to choose colours that read well (value contrast, a white's shadow, skin, hair lights, main and accent colours): [references/palette-design.md](references/palette-design.md).

- **The user names colours** ("silver hair, red eyes, a black coat"): write a card by the subject's part names, and `iris` for the eyes.
- **The user gives a colour card picture**: `python ../refinish/scripts/palette.py read CARD.png --out swatches.jpg` finds its flat swatches and numbers them on `swatches.jpg`; read the card's labels against the numbers. For swatches it misses, `--at x,y,name` reads the colour round each point.
- **A scheme, not a list** ("make her dazzling", "team red"): kinds (`hair`, `metal`, `cloth-white`) and roles (`main`, `sub`, `accent`) cover a figure without its part names, so one card fits many pictures.

Give the bases. Add a shadow, second shadow or highlight only where the user wants a particular one: the rest are derived, and `python ../refinish/scripts/palette.py derive "#c8442f" --kind skin` shows what a base gets.

Show the card before finishing: `python ../refinish/scripts/palette.py board CARD.json board.png --subject subject.json` draws each entry's four colours (a derived colour is marked `*`). Change it until the user approves.

### 3. Apply

```
python ../refinish/scripts/palette.py apply subject.json CARD.json carded.json
```

`carded.json` is the subject with the card written into its colour models. The report lists each recoloured part, its four colours and where they came from (`parts`, `iris`, `kinds`, `roles.main` ...), and the parts kept as drawn. A part the user named but the report does not list: its name differs on the card (the report's `kept_as_drawn` gives the subject's names).

### 4. Finish

```
python ../refinish/scripts/refinish.py carded.json tv-cel out.png
```

Any cel style takes a card: `tv-cel`, `heavy-cel`, `bold-ink-cel`, `film-everyday-cel`, `pastel-film-cel`, `cel-90s`, and the night and sunset variants (the Refinish skill's [presets.md](../refinish/references/presets.md)). The card's parts are painted in its colours exactly; the rest of the figure in the style's own. The other engines (paint, de-AI, duotone) ignore a card, and their report says so. Lines round a recoloured part take a dark shade of its new colour, and so does the line between hair and face.

The check runs on every result. Besides the Refinish checks, five are the card's:

| check | finds | usual cause | fix |
|---|---|---|---|
| RC1 | a part painted far from its card colour (CIEDE2000 over 3 WARN, over 6 FAIL; under `grade: style`, its hue over 15 degrees off WARN, over 30 FAIL) | the part holds another material, so its tones are split between two | fix the part map (step 1) |
| RC2 | a patch of a part still in its old colour | a line or a fleck the part map gave to another part | fix the part map; look at the box on the review picture |
| RC3 | an iris off the card's hue, or the two eyes recoloured unlike | the iris labelled hair or cloth, or part of it labelled skin | give the iris a part of kind `eyes` |
| RC4 (WARN) | patches of a part the card left alone, inside one it recoloured, that were drawn like it | the part map gave a piece of the recoloured part to its neighbour (a cream shirt's light folds read as the pale skin beside them) | give the patches to the recoloured part (a hint point), or name their part on the card |
| RC5 (WARN) | small pieces of a recoloured part far from it, inside another part, kept as drawn | the part map joined another thing to the part by colour alone (gold ornaments to blonde hair) | nothing, when they are another thing; when they are the part's (a strap cut off by an arm), `"pieces": "paint"` in its card entry |

All the checks: the Refinish skill's [checks.md](../refinish/references/checks.md).

### 5. Look

Open the result at full size beside the source, and the face at 1:1:
- the eyes: the lashes and the whites as drawn, the catchlights white, both irises alike;
- the lines: round a light new colour, dark enough to hold the shape;
- the edges between recoloured parts: no light seam, no rim of the old colour;
- every piece RC5 kept as drawn. A piece of something else is right as it is. A piece of the part itself (a fold of a hood showing between strands of hair, a strap cut off by an arm) stays in its old colour until the card says `"pieces": "paint"` or a touch gives it to the part.

A light colour on a part drawn dark (black hair made white) shows the drawing's strand marks more than the dark did: that is the drawing, not a fault. When the user wants it calmer, a darker or greyer shadow on the card softens it.

### 6. Touch

When the look finds a patch in the wrong colour (a reflection in an iris left in its old colour, lashes in the iris's colour, a strap kept as drawn), fix it with a touch rather than a new part map:

1. Read the patch's place off the result: `python ../refinish/scripts/palette.py zoom out.png x0,y0,x1,y1` enlarges the box round it with a grid of its coordinates.
2. Write `touch.json` ([references/palette-format.md](references/palette-format.md), "Touches"): a point on the patch and what it becomes, `as` a part, `keep`, or `to` a colour. Give a box to a patch with no line round it (a reflection that runs into the skin), and to every point on a lash or another dark line.
3. `python ../refinish/scripts/palette.py apply subject.json CARD.json carded.json --touch touch.json`, and look at `carded.touch.jpg`, each touch's reach: too large, lower its `tol` or give it a box; too small, add a point or raise its `tol`.
4. Finish again (step 4) and look again (step 5).

Two rounds settle most patches. Many patches, or a whole part wrong, mean the part map is wrong: go back to step 1.
