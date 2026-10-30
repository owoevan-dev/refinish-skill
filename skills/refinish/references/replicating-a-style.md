# Replicating a style by measurement

A reference picture's finish can be measured and written into a style file, then checked by measuring the result the same way. The loop is closed: no guessing from a description.

## What can and cannot be replicated

- **Can**: the finish. Line width, how dark lines are against their fill and whether they take its hue, how many lines are kept, the shading's flatness and the softness of its edges, chroma, texture.
- **Cannot**: the design. Proportions, the way eyes are drawn, the line structure itself and how many folds and strands the drawing has. The scene's light is not replicated here either: in a sunset picture most of the figure is in shadow because of the sky, not because of the style, and it moves the shadows' share and colour and the value range.

Tell the user this before starting. A request for "the style of X" gets X's finish on the user's own drawing, not a redrawing.

## The quick way: fit_style.py

`scripts/fit_style.py SUBJECT.json REF.png [REF2.png ...] --out STYLE.json` runs the loop below for you:
1. It measures the references and the subject at one height with the same stand-in parts.
2. It tries the bundled cel styles on the subject and starts from the nearest.
3. Each round moves every number more than 10 % off one step toward the references. A number that overshoots takes half steps after that.
4. It keeps the round with the most numbers within 10 %.

Its report lists every round and the numbers still off. Look at the result at full size beside a reference before showing it: the numbers are a guide, the eye decides. Run the loop by hand (below) when the references come with subject files, so the per-kind numbers (skin and cloth chroma apart, the shadow's colour) can be fitted too.

Tested on a closed loop: references rendered in a bundled style, fitted from another bundled style on a different character. Three rounds brought six of the eight finish numbers within 10 %. The two left were line density and line lightness, which follow the drawing as much as the finish.

## Words instead of references: tweak_style.py

A person often says what to change rather than giving a reference: "softer shadows", "more vivid", "線を太く", "陰影柔一點". For that, use `scripts/tweak_style.py STYLE.json OUT.json "softer shadows, more vivid"`. It changes each matched word's keys one step (`--steps N` for more). `--list` shows the words known, and `scripts/_adjectives.py` holds the table.

The report names the measured number each word should move. Measure before and after (`scripts/measure_style.py`) to confirm it moved, then look.

A word with no meaning for the style's engine is reported, not guessed. Words that name a design ("bigger eyes", "longer hair") have no entry: the finish cannot change the drawing.

## The loop

1. **References**: one to five finished pictures, ideally from one set. Cut each figure out. Give each a subject file (references/subject-file.md) so the per-kind numbers are measured on the figure alone.
   - A style is not someone's property; what is measured are numbers about the finish (line darkness, chroma, flatness), and the result's drawing is the user's own.
   - The pictures themselves stay where the user keeps them: never copy them into the project, the style file or anything shared. A style file holds numbers only, never a crop, a texture or a stroke taken from a reference.
   - A style written this way is named after its technique, never after the work or the artist it was measured from.
2. **Measure**: `scripts/measure_style.py REF.json --out m_ref1.json` for each, then `scripts/measure_style.py --profile m_ref*.json --out profile.json`. The median of each number is the target. Without subject files, `--auto-parts K` measures K hue clusters as stand-in parts; trust only the picture-wide numbers from them, since a cluster can hold two materials (white hair and the grey of its lines, a pale cloth and its dark print) and its shadow numbers then describe neither.
3. **Measure the subject**: `scripts/measure_style.py SUBJECT.json --out m_src.json`, and compare it with `--compare profile.json m_src.json --finish` to see how far the source is. When the references are much smaller than the subject (a model sheet 1000 px tall against a sprite 3000 px tall), measure the subject and every result at the references' scale instead: `scripts/measure_style.py PICTURE.png --at-height 1000`. Line width, edge softness and the darkness of thin lines all depend on the pixel scale; at the wrong scale they send the loop after differences that are not there.
4. **Write the style** from the nearest bundled style and the table below.
5. **Apply and measure**: `scripts/refinish.py SUBJECT.json STYLE.json out.png`, then `scripts/measure_style.py SUBJECT.json --image out.png --out m_r1.json`, and `--compare profile.json m_r1.json --finish`.
6. **Adjust** the parameter of each number off by more than 10%, one step each, and repeat 5. Stop after four rounds; keep the round with the most numbers within 10%, then look at it at full size beside a reference before showing it.

| number | parameter | direction |
|---|---|---|
| `line_hue_match` near 1 | `lines.colour`: `trace` or `own` | below 0.5: `ink` |
| `line_to_fill` | `lines.trace.dark` | about equal to it |
| `line_to_fill`, `line_width` already near the target in the source | `lines.colour`: `drawn` | the source's own lines kept; only the paint changes |
| `line_width` | `lines.strength`, `lines.cut`, `lines.outline.width`, `lines.outer` | strength and outline up for wider |
| `line_density` | `lines.keep.min_area_drawn`, `lines.cut` | up for fewer lines |
| `chroma.median` | `palette.chroma` | the ratio of the target to the result |
| chroma of skin and of clothes apart | `palette.kinds` | a figure-wide median mixes the design's share of skin and cloth with the finish; measure the two apart and set each |
| `texture` | `texture.grain` | up for more |
| `flatness_median` | `shading.harden`, `shading.soft` | harden up and soft down for flatter |
| `edge_softness_median` | `shading.soft` | up for softer |
| `shadow_shift` (from the most evenly lit reference) | `shading.derive` per kind | equal to it |

## A worked test

Three finished illustrations (our own) as references, one character generated to the cel spec as the subject, the cel engine. Finish numbers, target against the chosen round 3:

| number | target | source | round 3 |
|---|---|---|---|
| line_width (u) | 0.85 | 0.89 | 0.83 |
| line_to_fill | 0.59 | 0.45 | 0.65 |
| line_hue_match | 0.99 | 1.00 | 1.00 |
| line_density | 0.038 | 0.078 | 0.049 |
| chroma.median | 23.6 | 20.5 | 23.3 |
| texture | 0.58 | 0.47 | 0.59 |
| flatness_median | 0.69 | 0.67 | 0.68 |
| edge_softness_median (u) | 0.58 | 0.32 | 0.41 |

Six of eight within 10% after three rounds. Two were not reached:

- **Line density**: limited by the drawing. The subject has more folds and strands than the references' figures, and removing more lines starts removing drawing.
- **Edge softness**: the `soft` parameter moved it slowly, because `harden` keeps part of the source's crisp step. A softer target needs `harden` lowered with it.

At full size the result read closer to the references than the plain TV cel style: lighter coloured lines, softer shadows, the grain. It did not have the references' soft painted gradients, which came from their lighting pass as much as from their finish.

## A second test: a bold-ink TV style

Six official model sheets of a TV anime (about 1000 px tall, measured with `--auto-parts 6`), an original character generated with the finish described in words, the cel engine. Measured at the sheets' scale (`--at-height`), the generated source already matched the lines (`line_to_fill` 0.344 against 0.348, black ink at the core like the sheets) and the texture; it fell short on colour: skin 25.5 against 28.3, clothes 14.3 against 36.0.

- `lines.colour: drawn` kept every line and hatch as drawn; re-laying them as ink turned the fine hatching into heavy black strokes.
- `palette.kinds` raised the clothes about three times and the skin by a tenth; a figure-wide `palette.chroma` would have turned the skin orange.
- Deep teal at L 31 sits at the edge of sRGB, so the boost stops there and keeps the hue (`palette`); clipped channel by channel it had turned royal blue.
- The part map needed a family for pure black (the sheets' black shadow masses and keyholes), kept as drawn and never boosted; inside a large black mass the line finder sees no line, and the nearest dark family painted it teal.

After four rounds: clothes 37.1, skin 28.6, `line_to_fill` 0.33. Line width (1.67 against 1.38) and density stayed where the drawing put them.
