# Source spec: what to ask the image model for

Every style runs on any picture. A picture generated to this spec gives the cel styles a much better start, because the problems a finish cannot repair are made at generation:

- an edge with no line under a rim light (the line cannot be traced where it was never drawn);
- hair strands fused with a background of the same colour (no cut-out can separate what was painted as one);
- soft airbrushed gradients, which flat tones break into blotches.

Measured on one character generated with and without the spec, the outlined share of the silhouette went from 58% to 92%, and both sides lined evenly. Check a picture with `scripts/check_input.py` before choosing a style.

## For every style

- The figure on its own, on a transparent background (or a flat plain one); backgrounds generated separately, with no figure in them.
- The whole figure in frame with a margin, at the model's largest size.
- One key light, the same direction across a set of sprites. Rim lights, glows and coloured light are added afterwards, in compositing, where they can match the scene.

## Cel styles: level 2 (recommended)

Append this to the prompt, word for word (it names no artist or work):

```text
Rendering: a TV anime cel, as painted by an anime finishing department: clean line art of one even weight, like a traced animation drawing; flat colours; large expressive eyes with layered irises and a crisp catch-light; few, deliberate fabric folds. Full figure, centred, feet near the bottom edge.

Requirements, strict: the picture goes to an anime paint department to be finished, so it has to be easy to paint over.
- Light: one soft white key light from the upper left of the picture, and nothing else. No rim light, no backlight, no light from the right, no glow, no bloom, no sparkles, no coloured light.
- Lines: a continuous dark line runs along every outer edge of the figure, closed all the way round, on the lit side as well as the shadow side. Every boundary between two parts has a line too. Each line is a clean single stroke, never broken into sketchy pieces and never replaced by a light edge.
- Shading: each material has one flat base colour and one shadow colour; the shadow is a hard-edged shape that follows the forms. No airbrushed gradients, no soft blending. A second, darker shadow only in the deepest creases.
- Highlights: crisp hard-edged shapes only.
- Sheer tights and stockings: one flat base colour and one flat shadow shape, no gradient and no sheen. Patent leather, lacquer and metal: a flat base with two or three hard-edged highlight lines, no reflections of the surroundings.
- Hair: gathered into clear locks with defined, pointed tips; only a few loose strands, each drawn with its own line; no fine flyaway hairs or translucent wisps at the outline.
- Surfaces: clean local colours; knit, cloth and skin without texture, noise or grain; knit ribbing shown by a few lines only.
- No background, no shadow on the ground, no text, no logos, no signature, no border.
```

Level 1 (the light, line, hair and surface rules without the shading rules) keeps the model's usual soft shading; it fixes the one-sided lines but leaves gradients that blotch. The material sentence was added after both levels still came back with realistic sheer tights and patent shoes: models follow "flat" for cloth and skin long before they follow it for glossy and sheer materials, so name them.

## Paint styles

Looser: the figure separate and one key light are enough. Soft shading is fine; the paint engine re-masses it.

## Backgrounds

- No figures.
- Restrained light: avoid the dramatic orange-and-purple sunset, regular window-shaped light patches, glossy wet floors and the same detail density everywhere, the four habits that read as generated most often.
- Keep the perspective simple and the middle clear where figures will stand.

## When the picture already exists

Nothing has to be regenerated: `check_input.py` grades it, the cel styles run in `drawn` mode by default (the safest for any source), and its report says what to expect. Regenerating to the spec is the fix when the grade is "best effort" and the result matters.
