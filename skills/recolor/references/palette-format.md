# The colour card (`refinish-palette/1`)

A colour card is a JSON file. It names colours for a figure's parts and says how they are painted. Only `format` is required; everything else is optional, and a card that matches nothing changes nothing.

```json
{
  "format": "refinish-palette/1",
  "name": "winter",
  "parts": {
    "hair": "#efeae4",
    "coat": {"base": "#1e2340", "shadow": "#141833"},
    "scarf": "#c8442f"
  },
  "iris": "#d04040",
  "kinds": {"metal": "#c0c6cc"},
  "roles": {"main": "#4b3bd6", "sub": "#ff2d8a", "accent": "#18d2c8"},
  "shadow_rule": {"turn_cap": 12},
  "grade": "card",
  "lines": "follow"
}
```

## Entries

An entry is a colour as `"#rrggbb"` (or `"#rgb"`), sRGB, or an object:

| key | meaning |
|---|---|
| `base` | the lit colour (ノーマル): most of the part |
| `shadow` | the shadow (1号影), where the source drew the part's shadow |
| `deep` | the second shadow (2号影), the deepest of the drawn shadow, in the styles with three tones |
| `highlight` | the light (ハイライト), in the styles that paint lights (hair, gloss): on the brightest of what the source drew, a tenth of the part at most (the ring of light on hair, not a lit side) |

A slot left out is derived from the base (below). Give a slot only when the user wants that colour exactly.

## Which parts an entry reaches

Each part of the subject takes the first entry that reaches it:

1. **`parts`**: by the part's name in the subject file (case does not matter).
2. **`iris`**: every part of kind `eyes` that is an iris: named iris or pupil, or coloured or dark. A part named for the whites is never one.
3. **`kinds`**: every part of that kind: `skin`, `hair`, `eyes`, `cloth`, `cloth-white`, `cloth-dark`, `sheer`, `gloss`, `metal`, `accessory`. Of kind `eyes`, only the irises.
4. **`roles`**: the clothes and accessories left over (kinds `cloth`, `cloth-white`, `cloth-dark`, `sheer`, `accessory`, `gloss`, `metal`), largest first: the largest takes `main`, the next `sub`, every other `accent`. A role the card leaves out is skipped, not passed down.

Three things are never reached by `kinds` or `roles`, only by name:
- **a prop**: a part marked `"prop": true` in the subject file, something the character holds or carries (a brush, a cup, a sword, a bag). It isn't part of the costume, so a scheme leaves it alone;
- **a feature of the face**: a part whose name holds one of the words mouth, lip, lips, teeth, tooth, tongue, blush, brow, brows, eyebrow, eyebrows, lash, lashes, eyelash, eyelashes, nose, eye, eyes, eyelid or eyelids (`upper_lip`, `eyebrows`; not `clip`, `brown-coat` or `eyewear`), or an accessory lying mostly inside the protected boxes;
- **solid black ink**: an accessory part darker than CIELAB L* 20 with less than 8 of chroma (the spot blacks of an inked style, which the checks ask to be a part of their own).

Every part no entry reaches keeps the style's own colours.

## Derived colours

What a card leaves out is derived from the base in OkLCh (Oklab's lightness, chroma and hue), as colour designers turn a shadow: a step down in lightness, a little more chroma, the hue turned toward the ambient light's. Lightness L is 0 to 1, chroma C about 0 to 0.37, hue h in degrees. The settings, all changeable in `shadow_rule`:

| setting | default | meaning |
|---|---|---|
| `drop` | `[0.08, 0.04]` | the shadow's lightness: L − (0.08 + 0.04 L), about 10–12 of CIELAB L*, a TV colour model's step |
| `chroma`, `chroma_add` | `1.08`, `0.01` | the shadow's chroma: C × 1.08 + 0.01 |
| `cool_hue`, `turn`, `turn_cap` | `290`, `0.3`, `18` | the shadow's hue turned 0.3 of the way toward 290° (blue-violet, the sky's light), at most 18° |
| `skin_drop` | `[0.07, 0.03]` | skin's shadow, a smaller step |
| `warm_hue`, `skin_turn_cap` | `30`, `10` | skin's shadow turned toward 30° (red), at most 10° |
| `skin_chroma`, `skin_chroma_add`, `skin_chroma_cap` | `1.25`, `0.015`, `0.03` | skin's shadow richer, the more so the lighter the skin, never more than 0.03 above the base |
| `neutral`, `neutral_tint` | `0.03`, `0.025` | below 0.03 of chroma a colour is near-neutral; its shadow gets 0.025 of chroma at the cool hue (a white shirt's shadow is lavender-grey) |
| `deep` | `0.8` | the second shadow: the rule again from the shadow, its drop × 0.8, half the turn, no more chroma |
| `light`, `light_chroma` | `0.4`, `0.7` | the highlight: 0.4 of the way to white, its chroma × 0.7 |
| `light_hue`, `light_turn`, `light_cap` | `90`, `0.15`, `8` | the highlight's hue turned a little toward 90° (warm light), at most 8° |

When a hue lies straight opposite its target, it turns the warm way (a yellow's shadow toward orange, not green). Every colour that leaves sRGB is brought back by chroma alone, its lightness and hue kept (CSS Color 4's gamut mapping), never clipped channel by channel. Sources: [palette-design.md](palette-design.md).

## How the card is painted

- **`grade`**: `"card"` (the default) paints the card's parts in its colours exactly: the style's own colour grade (its contrast, lift and chroma) is eased off over them. `"style"` lays the style's grade over the card's colours too, as over every other part (a film style's soft contrast, a night style's dark); the check RC1 then compares the hue alone, since the style sets the lightness and the chroma.
- **`lines`**: `"follow"` (the default): the lines round a card's part take a dark shade of its new colour (色トレス), and the line between hair and face, and a strand drawn as a line across the face, the hair's. `"keep"`: the lines as the style draws them.
- **`pieces`**: `"keep"` (the default) or `"paint"`, for the whole card or in one part's entry (`{"base": "#c8442f", "pieces": "paint"}`). A part map joins some pieces to a part by colour alone: a book's gold ornaments to blonde hair, a jacket's silver buckles to silver hair, a shadow under the chin to dark hair. A small piece of a recoloured part (at most a twentieth of its body), far from it (40 u) and lying inside one other part (85% of the ring round it) is kept as drawn, so the new colour shows only where the part is; the check RC5 names each one. When such a piece is the part's own (a strap cut off by an arm), `"paint"` paints it with the part.

Before painting, the part map is mended for the card in one more way: an iris part's pixels that are the hair over the eye (the hair's colour, joined to the hair outside the eye's box without crossing a line) go back to the hair, or the hair over a dark iris would take the iris's new colour.

Inside the face's protected boxes the features stay as drawn: lashes, the whites, the catchlights, the mouth. The irises take the card's colour there by their own lightness, from the darkest of the pupil to the lightest of the iris, the catchlights left white. Only the iris takes it: an eye part drawn wide over the white of the eye or the skin colours only its iris, and a dark iris part joined to the lashes and the strands round it colours only its thick round mass in the eye's box; its strips narrower than the iris's own radius (the upper lash line, a lash's tail, a strand of hair) stay as drawn. Hair falling over an eye takes the hair's new colours.

## Touches (`refinish-touch/1`)

A result can show a patch the part map got wrong: a pale reflection in an iris given to the skin, an eye's lashes given to the iris, a strap kept as drawn. A touch file fixes such a patch from a point on it, without making the part map again:

```json
{
  "format": "refinish-touch/1",
  "touch": [
    {"at": [470, 378], "as": "irises", "tol": 20, "box": [455, 364, 488, 386]},
    {"at": [[1250, 650], [1300, 665]], "keep": true, "box": [1200, 635, 1360, 706]},
    {"at": [812, 1430], "to": "#c8442f"}
  ]
}
```

| key | meaning |
|---|---|
| `at` | a point `[x, y]` on the subject's picture (the enlarged one the subject file names), or a list of points |
| `as` | the patch is this part's: it takes the part's colours (the card's or the style's) and its rules, an iris's gradient map included |
| `keep` | `true`: the patch stays as drawn |
| `to` | the patch takes a colour of its own, an entry as on a card (a hex, or `{base, shadow, ...}`), its drawing carried onto that colour as an iris's is; `kind` (default `cloth`) sets how the colours it leaves out are derived |
| `tol` | how far (CIELAB, default 12) a colour may be from the colour at the point and still be reached |
| `box` | `[x0, y0, x1, y1]`: the patch stops at it |

Each point reaches the colour round it: the pixels within `tol` of the colour at the point, joined to the point without crossing a line. A point on a line (a dark thing the line finder reads as ink, such as lashes) reaches over the lines as well, inside its box or close round the point (20 u), so give it a box. The touches are applied last, over every other rule for the part map and the protected boxes. Where two touches reach the same pixels, the later one in the file wins. A `to` touch colours whites too (a white shirt), except a catchlight inside the protected boxes, which stays white.

`palette.py apply SUBJECT.json CARD.json OUT.json --touch TOUCH.json` writes them into the carded subject. Its report gives each touch's reach: `px`, `box`, `share` of the figure, and a `note` when the reach goes well beyond its points or, given to an iris, out of the eyes' boxes. `OUT.touch.jpg` shows each touch's reach tinted and numbered on the picture. Look at it before finishing: a reach far larger than the patch has run into the part beside it (lower `tol`, or give a `box`); one smaller than the patch needs another point or a higher `tol`.

To read the points off a result, `palette.py zoom RESULT.png x0,y0,x1,y1` enlarges that box with a grid of its coordinates: a point read off the whole figure is often a few dozen pixels off.

## Commands

All in `../refinish/scripts/palette.py`; each prints JSON, and stops with exit code 2 and a message on a card it cannot read.

| command | does |
|---|---|
| `apply SUBJECT.json CARD.json OUT.json [--touch TOUCH.json]` | writes the subject with the card in its colour models; reports each recoloured part's four colours and where they came from, and the parts kept as drawn; with touches, each touch's reach and a preview (above) |
| `zoom PICTURE.png x0,y0,x1,y1 [--out zoom.jpg]` | a box of a picture enlarged with a grid of its coordinates, to read a touch's points off a result |
| `derive "#c8442f" [--kind skin]` | the shadow, second shadow and highlight a base gets |
| `board CARD.json OUT.png [--subject SUBJECT.json]` | the card as swatches, one row an entry: base, shadow, second shadow, highlight, a derived one marked `*`; with the subject, each row derived for its part's kind |
| `read CARD.png [--out swatches.jpg]` | the flat swatches of a colour card picture, numbered on the preview |
| `read CARD.png --at x,y[,name] ...` | the colour round each point, for swatches `read` does not find on its own |
