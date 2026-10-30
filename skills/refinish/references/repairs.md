# Repairs: fixing a source without restyling it

`scripts/repair.py PICTURE.png OUT.png` fixes defects in a source picture by code and leaves its style as it is. Run
it before a finish when the source has them (the finish inherits a source's defects), or on its own when the user
only wants the picture cleaned.

```bash
python scripts/repair.py image.png repaired.png --subject subject.json
python scripts/repair.py image.png repaired.png --fix halo,specks --dry-run
```

Every change is marked on `OUT.repair.jpg` (halo blue, specks red, lines green, bleed magenta). Look at it: each
repair reports how much it changed and where, and a repair that changed more than expected is a reason to look before
using the result.

## The repairs

| repair | what it fixes | how | needs |
|---|---|---|---|
| `halo` | a cut-out's fringe: a light or dark rim of the background it was cut from | the semi-transparent edge takes the colour of the nearest pixel well inside the figure; where a fringe runs round more than a fifth of the edge, the outermost opaque ring too, and the matte is choked by a pixel where it runs round half | a cut-out |
| `specks` | small blobs foreign to a flat area: rendering noise, stray dots | a blob clearly off its area's colour, small, not elongated, in a flat area away from the outline and the lines (a sparkle in hair, a print, a corner where tones meet are left), is filled from its surroundings | nothing; with a subject, dark dots off the face too |
| `lines` | gaps in the line art | the line art is thinned and pruned; two stroke tips facing each other across a gap up to 5 u, or a tip facing a line, are joined with a stroke of the line's colour and width | nothing |
| `bleed` | colour that ran across a part's edge into its neighbour | near the border with a neighbouring part, pixels much nearer the neighbour's colours than their own part's, in a run that starts at the border, are repainted from their own part | a subject |

## Limits

- **Dark dots are features on a face.** A nostril, a mole or a beauty mark reads like a speck, and the line finder takes
  any small dark mark for line art. Without a subject only colourful dots are taken (line art is dark and dull); with
  one, dark dots too, but never on the face. Measured on a figure with 29 random specks: 19 found without a subject,
  none reported on the same figure clean; the misses were dark or line-coloured dots.
- **Not every gap is a mistake.** A strand's tip, a fold that stops short and a sketchy line are drawn with gaps. Only
  tips that face each other (within 30 degrees) across a short gap are joined; look at the green marks.
- **Bleed trusts the parts.** It repaints by the subject's part map, so a part map with a mistake is "repaired" into
  the mistake. Run it after the parts sheet is right, and look at every magenta mark.
- **A halo the edge does not show is not found.** The fringe is measured against the colour just inside the edge. A
  figure whose edge is drawn in a light colour (a white outline, a rim light) is reported as a light fringe: use
  `--fix` without `halo` there.
