# Recipes: local finishes and mixes

`scripts/recipe.py RECIPE.json OUT.png` lays several finishes over one picture: a base finish, then layers of other
finishes, each limited to some parts or areas of the picture and blended in. Every finish is rendered once, as
`scripts/refinish.py` renders it (the guard, the style's own layers, the checks), and then mixed.

Use it when one style is right for most of the picture and wrong for a part of it, or when the look the user wants
lies between two styles.

## Contents

- The recipe file
- Where a layer applies
- Blend modes
- Examples
- Gotchas

## The recipe file

```json
{
 "format": "refinish-recipe/1",
 "subject": "subject.json",
 "base": "tv-cel",
 "layers": [
  {"style": "watercolour", "where": ["cloth", "cloth-white", "cloth-dark"], "opacity": 1.0, "feather": 2}
 ],
 "post": [{"op": "grain", "amount": 0.015}],
 "hour": "sunset"
}
```

| key | meaning |
|---|---|
| `subject` | the subject file, relative to the recipe |
| `base` | the finish under every layer: a bundled style's id, a style file's path, or `"source"` (the picture as it is). Default `"source"` |
| `layers` | in order, bottom to top. Each: `style` (as `base`), `where` (below), `blend` (below, default `normal`), `opacity` (0..1, default 1), `feather` (the mask's edge softness in u, default 1.5; 0 for a hard edge) |
| `post` | layers laid over the mix, as in a style file (references/style-format.md): `paper`, `grain`, `halation`, `soften`, `curve`, `focus`, ... |
| `hour` | relights the mix for another hour (`night`, `sunset`, `dusk`, `film-night`) |

A pixel style cannot be mixed: its sprite is a picture of another size.

## Where a layer applies

`where` is a list of words, or `{"only": [...], "not": [...], "box": [x0, y0, x1, y1]}`. Left out, or `"all"`, it is
the whole figure. A word is:

- a part's name in the subject file (`"skirt"`, `"hair"`);
- a kind: `skin`, `hair`, `eyes`, `cloth`, `cloth-white`, `cloth-dark`, `sheer`, `gloss`, `metal`, `accessory`, and in
  a scene `sky`, `far`, `water`, `foliage`, `ground`, `wood`, `roof`, `stone`, `wall`;
- an area:
  - `face`: the focal ellipse round the face and the eye and mouth boxes;
  - `eyes`, `mouth`, `features` (both): the protected boxes;
  - `lines`: the source's line art;
  - `outline`: a band 3 u wide inside the figure's edge;
  - `figure` or `all`.

`{"only": ["hair", "skin"], "not": ["eyes"]}` is the hair and the skin without the eye boxes. A word that is none of
these stops the run before anything is rendered, and the message lists the names it knows.

## Blend modes

On the picture's own values, as a paint program blends layers:

| mode | what it does | typical use |
|---|---|---|
| `normal` | the layer over the base | a part in another finish |
| `multiply` | darkens by the layer; white leaves the base as it is | a screentone or a pencil drawing over colour |
| `screen` | lightens by the layer | a glow, a light finish over a dark one |
| `overlay`, `soft-light` | contrast from the layer, colour from both | a texture or a grade |
| `darken`, `lighten` | the darker or lighter of the two | lines over a wash |
| `colour` | the layer's hue and chroma on the base's lightness | one finish's palette on another's shading |
| `lightness` | the layer's lightness under the base's colour | one finish's shading in another's palette |

## Examples

**The clothes in watercolour, the face and hair in TV cel.** The cel finish keeps the face crisp at small sizes;
the clothes take the wash.

```json
{"format": "refinish-recipe/1", "subject": "subject.json", "base": "tv-cel",
 "layers": [{"style": "watercolour", "where": {"only": ["cloth", "cloth-white", "cloth-dark", "accessory"]}, "feather": 2}]}
```

**A manga screentone over watercolour.** The tone's lines and dots multiplied over the wash: white paper leaves the
colour as it is.

```json
{"format": "refinish-recipe/1", "subject": "subject.json", "base": "watercolour",
 "layers": [{"style": "manga-screentone", "blend": "multiply", "opacity": 0.8}]}
```

**Between two styles.** A heavy cel with 30 % of the film everyday look over it, everywhere but the eyes.

```json
{"format": "refinish-recipe/1", "subject": "subject.json", "base": "heavy-cel",
 "layers": [{"style": "film-everyday-cel", "opacity": 0.3, "where": {"not": ["eyes"]}}]}
```

**Only part of the picture re-finished.** The picture as drawn, its hair cleaned of rendering noise.

```json
{"format": "refinish-recipe/1", "subject": "subject.json", "base": "source",
 "layers": [{"style": "deai-strong", "where": ["hair"], "feather": 1}]}
```

**A scene in two finishes.** A woodblock sky over an ink-wash landscape.

```json
{"format": "refinish-recipe/1", "subject": "scene/subject.json", "base": "ink-wash-scene",
 "layers": [{"style": "woodblock-scene", "where": ["sky"], "feather": 6}]}
```

## Gotchas

- The checks run on each finish, not on the mix. A mix inherits the mistakes of its finishes: fix the subject file,
  not the recipe.
- Two finishes with different lines (a cel's coloured trace, a watercolour's faint pencil) meet at the mask's
  edge. Mask by whole parts, so the seam falls on a drawn line; a `feather` of 1 to 3 u hides the rest.
- `opacity` below 1 over a finish with other lines doubles the lines faintly. To mix two looks everywhere, prefer
  styles with the same line colouring, or blend with `colour` or `lightness`.
- Paper and grain belong to the mix: put them in the recipe's `post`, not in two layers' styles, or they are laid
  twice.
