# The input check

`scripts/check_input.py` grades a source before a style is chosen. Its numbers are measured, not judged by eye.

| number | how it is measured | what it predicts |
|---|---|---|
| `outline` | for each edge pixel of the cut-out, whether the darkest pixel within a few source pixels inside it is clearly darker than the fill 8 to 16 source pixels further in (15 L darker, or below 60% of it); split by edges facing left and right | where the cel styles have to draw the outline themselves; a large gap between the sides is a rim light or a lit side |
| `flatness` | per part, the share of its lightness variance explained by its own two tones (three for hair and gloss) | how cleanly flat tones fit: low values blotch when posterised |
| `misfits` | thick dark blobs labelled as a light part, large light blobs labelled as a dark part | mistakes in the part map, to fix before painting |
| `figure_px` | the cut-out figure's height | whether to enlarge first (below 2000 px) |
| `cut_out` | a transparent background over at least 5% of the picture | whether the cel styles can run (they need the figure on its own) |

## Grades

- **cel / supported**: a cut-out; at least 65% of the outline drawn, the two sides within 12 points of each other; mean flatness at least 0.62.
- **cel / best effort**: one of those fails. The style still runs: the closed outline is drawn where lines are missing, but a rim light's colour stays in the fill, and soft parts may blotch.
- **cel / not advised**: no cut-out. Use a paint style for the whole picture, or generate the figure separately.
- **paint / supported**: any picture; below 1000 px the strokes get coarse.

## Where the thresholds come from

One character, one pose, generated three ways and measured (outline all / left / right; mean flatness):

| source | outline | flatness |
|---|---|---|
| no spec (a rim light from the right) | 58% / 64% / 53% | 0.66 |
| source spec level 1 (light and lines) | 77% / 79% / 75% | 0.68 |
| source spec level 2 (cel shading too) | 92% / 92% / 91% | 0.67 |

The outline separates the three clearly. Mean flatness does not separate the two spec levels, although level 1's hair and shoes blotched visibly and level 2's did not: treat flatness per part (hair, gloss) as the better signal, and the thresholds as provisional until more pictures are measured.
