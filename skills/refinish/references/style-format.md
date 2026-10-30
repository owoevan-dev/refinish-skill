# Style files

A style file is everything a style decides about the finish of a picture, as numbers: how shadows are shaped and coloured, how lines are found, kept and coloured, the palette, touches and texture. Every engine reads the same format; the `engine` key says which one paints it (`cel`, `paint`, or one of the engines built on a cel finish below).

```json
{
 "format": "refinish-style/1",
 "id": "tv-cel",
 "name": "TV anime cel",
 "engine": "cel",
 "summary": "One sentence a person can check the result against.",
 "shading": { "...": "defaults for every part" },
 "kinds": { "hair": { "...": "overrides for hair" }, "skin": { } },
 "palette": { }, "lines": { }, "touches": { }, "texture": { }
}
```

## Units

Lengths are in **u**, a thousandth of the subject's height: the cut-out figure's own height, or the picture's height when it is opaque. Areas are in **u²**. One style file therefore paints a 1500 px sprite and a 3000 px one alike. On a figure 3000 px tall, 1 u is 3 px.

## Kinds

Rules are written per kind of part, never per part name, so a style works on any character. A subject file gives each part a `kind`:

| kind | for |
|---|---|
| `skin` | face, hands, legs |
| `hair` | hair, fur, a plush's hair |
| `eyes` | irises and the whites of the eyes (kept as drawn through the protected boxes) |
| `cloth` | coloured cloth (the default) |
| `cloth-white` | white or near-white cloth |
| `cloth-dark` | navy, black or other dark cloth |
| `sheer` | tights, stockings, veils: soft gradients by nature |
| `gloss` | patent leather, lacquer, plastic with shine |
| `metal` | buckles, armour, jewellery |
| `accessory` | small objects of several colours (headphones, a badge): usually kept as drawn |

A part's rule is the style's `shading`, then the style's rule for its kind, then the subject's own rule for that part, merged key by key (nested objects too).

## The same-material guard (every engine that paints by parts)

Before any engine paints by parts, `scripts/_guard.py` gives back to its part what a part map put in the wrong one:
each part's material is read as the few colours most of its pixels have, away from its borders; a run of pixels far
from all of them that matches another part's material goes to that part when it touches it (across a line at most),
or whatever it touches when the run is large (a forearm cut off from the skin by a rolled sleeve and labelled as the
sleeve). A run inside the skin that matches nothing (the dark inside of a coat labelled skin) is kept as drawn. The
result's `guard` lists the moves. A style may tune or turn it off in a `guard` section:

| key | default | meaning |
|---|---|---|
| `on` | true | false: paint the part map exactly as given |
| `out_ab`, `in_ab`, `margin` | 12, 7, 5 | a pixel is a stray when it lies farther than `out_ab` from its part's colours (a*b*, lightness at 0.3), and goes to another part when it lies within `in_ab` of that part's colours and `margin` nearer than to its own |
| `min_area`, `far_area`, `far_kinds` | 2, 40 u², [skin, hair] | the smallest run moved; the smallest run moved to a part it does not touch, and only into a part of these kinds, and only when the run is less than half that part's size (a draft's small patch of facial shade must not take a knee's flush) |
| `keep_strays` | `skin` | where a run matching no part is kept as drawn: `skin`, `true` (every painted part; a part's own highlights would keep their soft rendering too), `false` |

## The cel engine

### shading (per part)

| key | default | meaning |
|---|---|---|
| `model` | `part` | `part`: painted from a colour model. `regions`: one flat colour per region its lines enclose. `keep`: left as drawn. |
| `follow` | `drawn` | `drawn`: shadow shapes where the source drew them (its tones found by clustering). `form`: the darkest `share` of the part at the scale of its forms; for soft sources with no shapes of their own. |
| `tones` | 2 | 2: base and shadow. 3: base, shadow and a deeper second shadow (二影) inside it, coloured `deep` = [dL, da, db] from the shadow (default [-12, 3, -3]); `drawn` finds it as the darkest drawn tone, `form` as the darkest `deep_share`; its islands below `deep_min_island` (u², default twice `min_island`) are dropped, so on dark hair it forms a few masses instead of flecks. 1: flat. |
| `harden` | 0.85 | `drawn`: how far each pixel is pulled to its flat tone (1 replaces it; the rest keeps the source's fine marks). |
| `scale` | 1.0 u | `drawn`: the edge-preserving smoothing's reach. `form`: the form blur. |
| `range` | 0.05 | `drawn`: the smoothing's range in lightness (0..1); larger smooths across softer steps (sheer cloth: 0.3). |
| `deblotch` | none | `drawn`, per part in the subject's `rules`: read the part's shading through a blur of this many u (4 is a good start) before the tone cut. For a part airbrushed in one tone, whose shadow comes out in blotches because the cut follows the picture's noise (a matte black); a wider `range` does not cure it. Never in a style: on a part drawn in tones (a strand's shadow, a pleat's, a knit's bands) it blurs the drawing, and no measure of a part's lightness told the two apart reliably. |
| `auto_deblotch` | off | `drawn`: a number (18 is a good start) turns the broader reading on for the parts whose own two-tone cut comes out ragged (`core.cut_raggedness` above it) and whose two tones lie less than `auto_deblotch_contrast` (0.25, in L/100) apart, so a printed pattern is left alone; it tries 3, 6 and 10 u and takes the smallest that is clean, and the shadow keeps its share of the part. Never on hair. In a style or a part's rule; see adjusting.md |
| `share` | 0.35 | `form`: the part's share in shadow. |
| `smooth` | 0.4 u (`form`: 1.0) | how much the shadow's outline is smoothed. |
| `min_island`, `min_hole` | 4.4 u² (`form`: 33, 22) | shadow islands and holes smaller than this are dropped or filled. |
| `min_depth` | 0 | a shadow must be this much darker (L 0..1) than the part's middle (keeps a knee's pink from becoming a bruise). |
| `soft` | 0 | blur of the shadow's edge, u (a film style's softer turn). |
| `shadow` | `own` | `own`: the source's shadow colour, tinted by `tint` × `tint_amount`. `derive`: the base shifted by `derive` = [dL, da, db] in Lab. |
| `base_pct` | none | the base colour taken at this percentile of the part's lightness (a darker base for black gloss); dark parts (median L below `dark_below`, 0.33) use `dark_base_pct` (25). |
| `minor_light` | 0.25 | `drawn`, two tones, no highlight: on a dark part (median L below `dark_below` + 0.07), a lighter tone holding less than this share of it is wear or sheen (worn leather, a satin strap), not its base; base and shadow are read from the rest and the light patches take the base. Without it, worn leather comes out mottled, its own colour painted as the shadow. A light patch larger than `minor_max_patch` (1500 u²) is another material sharing the part, and the rule is not applied. |
| `highlight` | none | `{"mode": "crisp"}`: a hard-edged light shape (`smooth` u, `min_island` u²). `{"mode": "band", "band": {"soft": u, "alpha", "lift"}}`: one soft lighter band. `drawn` finds the light as the third tone; `form` takes the top `share`. |
| `base_lab`, `shadow_lab`, `deep_lab`, `highlight.colour_lab` | none | a colour model given outright (Lab), as a colour designer's sheet gives it, instead of the one read from the picture; the shapes still come from the picture. A character's own colours belong in the subject file's `rules`. |

### lines

| key | default | meaning |
|---|---|---|
| `finder` | `{"simplify": [3, 9], "lo": 0.18, "crisp": [0.15, 0.6]}` | the line finder: mean-shift radius and colour range, the weakest response kept, and (for an enlarged `form` source) the two cut points that make soft line edges crisp. |
| `keep` | `{"min_area": 6.67, "min_area_drawn": 0.67, "kinds": {"hair": 44}}` | the smallest line kept, u² (`form` / `drawn`); per kind with `kinds` for `form` and `kinds_drawn` for `drawn`. Every line touching the face is kept. With an `ink` colour, `kinds_drawn: {"hair": 30}` keeps the long strands and leaves the short strand marks in the hair's own dark colour; inked, they read as black dashes. |
| `cut`, `strength` | 0, 1.0 | weak line responses dropped; the lines' opacity. |
| `grow` | 0 | every line widened by this much on each side, u (a style with heavier lines than the source drew). |
| `jitter` | 0 | every line moved off the drawing by slow noise of this size, u: a hand-traced cel's line (0.3 to 0.4). |
| `outline` | none | `{"width": u, "smooth": 3}`: one closed line of even width round the figure, on the lit side too; not along an edge where the picture cuts the figure off (a bust). |
| `outer` | none | `{"thicken": u, "band": u}`: lines near the silhouette drawn heavier. |
| `colour` | `own` | `own`: each line a dark shade of its own drawn colour, at `own.L` lightness × `own.chroma`, and at least `own.gap` (9) darker than the paint beside it, so a line on black tights or black hair still shows (two crossed legs stay two). `ink`: one ink `ink.ink` (Lab), `ink.skin` by skin, `ink.kinds` per kind. `trace`: the fill's darker shade (色トレス), `trace.dark` × fill L capped at `trace.cap`, `trace.chroma`, and `trace.neutral_bias` ([da, db], default [3, -8]: lines between near-neutral fills lean blue-violet; [0, 0] keeps their own hue); `trace.kinds` per kind. `drawn`: the source's own lines kept exactly (shapes, weights, soft edges, fine hatching), in the ink `drawn.ink` (Lab, default [2, 0, 0]) over the new paint; for a source whose line art already matches the target, so only the paint changes. |

### palette, touches, texture

- `palette`: `pivot`, `contrast` (L about the pivot), `lift` (added to L), `chroma` (multiplied); `palette.kinds` overrides `contrast`, `lift` or `chroma` per kind (a style whose clothes are far more vivid than its skin: measure the two apart). A boost stops at the edge of sRGB with the hue kept, so a deep colour gains less than the factor asks.
  - `palette.kinds.<kind>.chroma_target`: a chroma to reach instead of a factor, per part: each part of that kind is multiplied by the target over its own median chroma, held within `chroma_range` ([0.8, 2.2] by default). One factor treats a dull navy coat and an already vivid red one alike; a target brings both to the style's level (a bold TV style's clothes about 36).
  - `palette.light_ease`: [L0, keep]: above lightness L0 the change in chroma fades, to `keep` of itself at L 100, so pale colours (a mint shirt, a lilac cardigan) are not pushed toward neon by a boost meant for the mid tones. `palette.features` (`pivot`, `contrast`, `lift`, `chroma`) moves the features kept as drawn (the protected eyes and mouth, and the parts of kind `eyes`) with a changed colour model; with it, hair caught in a protected box takes the new hair colours.
- `touches.blush`: `alpha`, `colour` (RGB multiplier), at the subject's `blush` spots.
- `touches.cast`: a list of `{"from": kind, "onto": kind, "offset": [dx, dy] u, "smooth": u, "min_island": u²}`: one part's shadow on another, in the receiving part's shadow colour: the shape of `from` moved away from the light by `offset`, where it lands on `onto` (the fringe's shadow on the brow and the eyelids, a side lock's on the cheek).
- `texture.grain`: a fine grain's strength (0.01 to 0.02 is visible).

## The paint engine

`shading` and `kinds` take the masses' `share`, `scale`, `smooth`, `min_island`, `min_hole`, and per kind: `detail` (0..1, how much of the source's small shapes survive), `keep` and `keep_lit` (how much of each mass's value spread is kept), `temperature`, `stroke_direction` (degrees), `stroke_follow` (0..1, how much strokes follow the picture's grain), `stroke_vary`.

| section | keys |
|---|---|
| `pieces` | `size` (u, the superpixels), `merge` (how freely pieces merge outside the focal areas) |
| `palette` | `k` (colours), `pull` (toward them); `--palette-from` adds a scene's colours |
| `values` | `light_shift`, `shadow_shift` (Lab, added to lit and shaded pieces) |
| `strokes` | `scale`, `grain` (u, the structure tensor's reach) |
| `touches.light` | `kinds`, `share`, `density`, `lift`, `length` (u), `width` (u) |
| `edges` | `soft` (edges lost in the shade) |
| `lines` | `colour` (`trace`), `strength`, `dark`, `cap`, `chroma`, `shade_keep`, `face_only`, `outer`, `min_area` (u²) |
| `texture` | `grain`, `face_detail` |
| `seed` | the strokes' random seed |

## The de-AI engine (no parts)

`deai` keeps the picture's own colours and drawing and takes out the rendering tells of an image model: the noisy
micro-detail, airbrushed gradients, soft lines, a little too much chroma. It is framed as finishing quality, never as
hiding where a picture came from. It needs **no hints**: it works on the region map `scripts/auto_parts.py` writes
without any (the areas the picture's lines enclose), and keeps the eyes and the mouth that run finds as drawn.

Section `deai`:

| key | default | meaning |
|---|---|---|
| `flatten` | 0.55 | how far each pixel is pulled to its area's tones (light about 0.55, strong about 0.9) |
| `tones` | 3 | 2: shadow and base per area; 3: with a light where one clean bright shape stands apart |
| `guard` | [10, 24] | ΔE: a pixel within the first of its tone is pulled fully, beyond the second not at all; a strand, a stitch, a freckle that no area holds stays as drawn |
| `same_ab`, `guard_ab` | 6, [6, 13] | a*b*: two colours are one material in light and shade when their hue and chroma are this near; areas fold together, flecks go into their area and pixels are pulled toward their tone only within one material. Lightness is free, hue and chroma are not: pink hair over a red hoodie is only 24 apart in Lab, but 21 apart in a*b* |
| `mix_ab`, `max_colours` | 4, 6 | an area's tone whose pixels spread wider than `mix_ab` in a*b* holds several colours (a print, a camouflage, a trim whose line is faint): it is split into up to `max_colours` colour clusters, each with its own colour, so no two materials are averaged into a third |
| `noise`, `smooth` | 5, 0.8 u | the edge-preserving smoothing (bilateral, in Lab) before anything else |
| `step`, `min_share`, `max_share`, `min_area` | 7, 0.08, 0.65, 40 u² | when an area gets a shadow tone |
| `speck_share`, `speck_size` | 0.3, 3 | an area whose tones lie mostly in small pieces keeps one tone |
| `detail_area` | 60 u² | areas smaller than this fold into the area round them |
| `despeckle` | 0 | strong: small bright flecks inside an area (away from lines and edges) go to the area's tone, u² |
| `skin_soft` | 1.2 u | on skin (the automatic draft's), the tones meet softly (a blush, the shade under a fringe) |
| `lines` | `drawn` | `drawn`: the source's lines as they are; `crisp`: a dark shade of their own colour, with `outline` (u) closed round the figure |
| `chroma` | 1.0 | a slight restraint (0.94 to 0.97) |

The engine has its own check, **H1**, run after every finish: a patch of paint (off the lines and the outline)
whose a*b* moved more than 8 (after the style's own `chroma` factor) means a material was painted in another's
colour. Within a material the finish moves a colour's a*b* by about 6 at most, so an H1 patch is a fault worth
looking at; a borderline one (a highlight flattened into a darker tone) can still show, and is worth a glance.

Known limit: hair rendered as a mass of fine glints (a detailed painting) keeps some pale flecks under the strong
setting; the light setting suits it better.

## The duotone engine (no parts)

`duotone` puts the figure in two or three inks, or in a gradient of a few colours. Under them lies a flat finish named
in `base` (default `deai-strong`, which needs no parts; a cel style works too when the subject has them).

Section `duotone`:

| key | default | meaning |
|---|---|---|
| `mode` | `gradient` | `gradient`: each pixel's lightness looked up in `stops`, interpolated in Lab (a gradient map; sepia, cyanotype). `tone`: each ink laid by its own `curve` over the tone (a printer's duotone). `separate`: the base's colours matched by the inks printed over each other (a two-colour separation). `auto`: the picture's own two colours, the figure read as one material by the cel engine (`base` then a cel style, default `tv-cel`) |
| `stops` | none | `gradient`: `[[t, colour], ...]`, t from 0 (the darkest) to 1 (the lightest); a colour is Lab or `"#rrggbb"` |
| `levels`, `gamma` | [0, 1], 1.0 | the tone (the base's L / 100) stretched from `levels` to 0..1, then raised to `gamma` (above 1: a contrastier print, as a cyanotype is) |
| `inks` | none | `tone`, `separate`: `[{"colour": Lab or "#rrggbb", "curve": [[t, coverage], ...]}]`; the colour is the ink's printed look on white paper; `curve` only for `tone` |
| `paper` | `"#ffffff"` | a sheet kind (`newsprint`, `cold-press`, ...) or a colour: the inks print over it, darker and warmer on a cream sheet |
| `weight_L`, `steps` | 1.5, by ink count | `separate`: lightness counts this much more than hue in the match (a two-colour page reads by its values); the coverage grid's steps |
| `screen` | `flat` | `flat`: continuous. `halftone`: each ink's dots at its angle (`angles`, default [45, 75, 15]: the darkest ink at 45, 30 degrees apart against moire), `cell` (u), `spot`, `solid_above`, `offset` (u, off register). `riso`: a stencil duplicator's stochastic grain (`grain`, u), the drums `offset` (u) off register, the ink `uneven` |
| `sheet` | none | `{"kind": paper kind, "tooth": 0.05}`: the paper's tooth, lit, over everything printed |

A colour in a preset is the ink's printed look, approximate: a riso ink's or a spot colour's published swatch is
itself an approximation, and the paper changes it. Lines come from the base: in `gradient` and `tone` they take the
darkest stop or ink, in `separate` the inks that print dark together (black, or pink and blue over each other).

## Engines built on a cel finish

`pixel`, `tone`, `print`, `woodblock`, `wash` and `pencil` start from a cel finish of the figure, made with the style
named in `base` (a bundled style's id or a path; default `tv-cel`), and read its flat tones per part (base, shadow,
light). Their own section in the style file:

| engine | section | keys |
|---|---|---|
| `pixel` | `pixel` | `height` (px), `outline` (`selout` or `dark`), `colours`, `folds_from` (the height from which drawn folds are kept). Writes the palette beside the sprite as a `.hex` file. An eye under 4 px tall becomes a mark: 1–2 px wide (from the eye's dark extent), 2–3 px tall, in the iris colour darkened, with a ring of skin left, right and below it, so a fringe's shade does not swallow it into goggles |
| `tone` (manga) | `tone` | `cell` (u), `angle`, `levels` (the densities a tone may take), `white_below` and `black_above` (a base lighter than this stays paper, darker goes solid black), `shadow_step`, `skin_shadow` (a light skin's shadow), `skin_paper_below` (a skin lighter than this density stays paper: 0.35; a darker one takes a plain dot tone), `skin_tone_scale` (that tone as a share of its density: 0.65), `line_grow` (u), `outline` (u), `paper` and `ink` (L), `blush` (hatching, true/false), `white_lines` (true: the lines inside solid black drawn in white, as a manga artist does, so overlapping black shapes stay apart; hair keeps its shine instead), `white_line_margin` (u, how far inside the black a line must lie, 1.5), `white_line_min` (u², the shortest white line, 20: flecks of fold stay black). Parts of one density get different patterns (dot, line, cross, sand) |
| `print` (screen print) | `print` | `inks` (a number, or a list of Lab colours; the darkest is the key), `cell` (u), `angles`, `solid_above`, `offset` (u, off register), `uneven`, `paper` |
| `woodblock` | `woodblock` | `pigments` (name to Lab, replacing the period's; 黄土 yellow ochre among them), `sumi_below` (a part darker than this prints in sumi: 30, in a scene 12, where dark is mostly shade; dark cloth with a colour, at least `sumi_chroma` (10) and lighter than the sumi itself, prints in its pigment at full strength instead, as a navy skirt in indigo; hair keeps the sumi), `grey_chroma` (in a scene, a cool area (hue 200–320°) with more chroma than this prints in its pigment, not in sumi: 12; elsewhere 8), `scene_sumi_cap` (a large area printed in sumi in a scene, a night's stone, at most this strength: 0.8), `sumi_floor` (blocks over each other saturate at the sumi's darkness less this, 2), `skin` (a light skin's strength), `pale_above` (a skin lighter than this L is printed near the paper, the period's convention; a darker one blends to its own value over the next 14 L: 74), `bokashi`, `grain`, `offset` (u), `line_width` (u), `min_line` (u², the shortest line cut; 60 in a scene), `outline` (u), `paper`, `white_lines` (true: a line inside a block printed nearly as dark as the sumi is left uncut, 白抜き, so the paper shows along it; hair, skin and the face keep their sumi lines; off in a scene), `white_line_below` (L above the sumi under which a block counts as that dark, 10), `white_line_margin` (u, 1.5), `white_line_min` (u², 20). In a scene the key block also bounds every area of colour but the sky and the far hills |
| `wash` | `wash` | `medium` (`watercolour` or `ink`), `paper`, `edge`, `edge_width` (u), `granulation`, `flow`, `dispersion`, `bloom`, `bleed` (u), `wobble`, `glaze`, `light_paper`, `lines` (0..1), `line_colour` (Lab), `dry` (ink), `tones` (ink: five lightnesses), `accent_kinds` (ink: kinds kept in colour), `floor` (washes over each other saturate at this lightness: ink its darkest tone less 2, watercolour 20), `min_reserve` (u², 6: a light smaller than this keeps its wash instead of being left as paper; a dark part's lights are a thinner wash, never bare paper). The shadow glaze is read and laid off the line art (a white shirt's fold lines are not its shadow), and a dark wash (L below 45) stays inside its own part instead of wobbling onto a light neighbour. In ink, an interior's large areas (a scene with under 4 % sky; areas over 4 %) take at least the middle tone: the dark inks are kept for accents, not walls |
| `sticker` | `sticker` | `border` (u, 18), `round` (u, how far the cut closes the outline's notches, 14), `colour` (RGB, the vinyl), `edge` (RGB of the cut edge's thin line, or null), `shadow` (`offset` [dx, dy] u, `blur` u, `opacity`), `sheen` (0..1). **The picture grows** by the border and the shadow, so the result is larger than the source |
| `neon` | `neon` | `tube` (u, the tube's width, 2.4), `glow` (u, 9), `core` (0..1, how white the tube's centre burns), `fill` (0..1, how much of the fill's colour shows), `ground` (RGB, the dark the fills sink to), `min_line` (u², the shortest line kept; a face's lines are always kept), `outline` (the silhouette as a tube), `halo` (0..1, how far the glow reaches into the transparent ground), `face_pale`, `face_thin`, `face_dim` (on the face the tubes lose this share of their saturation, width and glow: 0.55, 0.4, 0.6, so a face reads by its lines and does not glow into one mass). Each tube takes the hue of the part beside it at full saturation; a grey or black part's tube burns white. **The picture grows** by 3 × `glow` |
| `glass` (stained glass) | `glass` | `piece` (u, the side of a typical piece, 70), `lead` (u, half the came's width, 0.8), `lead_colour` (RGB), `paint` (0..1, the grisaille trace lines' strength), `saturation`, `light` (0..1, how luminous the glass), `vary` (how much the sheets differ in lightness and hue), `texture`, `grisaille` (kinds painted on whole glass instead of cut: skin, and eyes in the bundled style; painted parts meet without lead) |
| `papercut` | `papercut` | `simplify` (u, how much a cut edge is smoothed, 2.5), `min_piece` (u², 25), `shadow` (`offset` [dx, dy] u, `blur` u, `opacity`), `fibre` (0..1), `paper` (the sheets' texture), `chroma`. Sheets are laid bottom to top, the largest parts first, each part's base tone under its other tones |
| `drawing` (charcoal, pastel) | `drawing` | `medium` (`charcoal` or `pastel`), `paper` (RGB), `tooth` (0..1), `hatch` (u, the strokes' spacing), `angles` (degrees, one per tone, light to dark), `strength`, `lines` (0..1), `lift` (0..1, white chalk on the lights), `smudge` (u). Charcoal draws the values; pastel covers by how far each colour is from the paper, so light colours on toned paper are laid thick |
| `pop` (Ben-Day pop art) | `pop` | `inks` (name to RGB: red, yellow, blue, black), `paper` (RGB), `cell` (u, the dot grid's spacing, 9), `angles` (one grid, 45), `levels` (the coverages a dotted ink may print at, besides solid and none: 0.18, 0.3, 0.42, so the dots stay round and apart), `line_grow` (u), `outline` (u). Each tone of each part is matched to the nearest overprint of the inks; at most two inks are dotted in one tone, their dots set side by side on the one grid (a light skin is red and yellow dots on white). `spot_above` (delta E, 10): a skin whose nearest overprint is farther than this (a tan, a brown) prints in a spot ink of its own colour, its shading in black dots. The eyes and the mouth are painted flat |
| `pencil` (key drawing) | `pencil` | `graphite` (Lab), `strength`, `tooth`, `min_line` (u²), `outline` (u), `colour_width` (u), `colour_strength`, `shadow_colour`, `light_colour`, `deep_colour` (Lab; by default the common convention: shadow blue, highlight red, second shadow yellow-green; studios differ), `hatch`, `hatch_spacing` (u), `paper` |

Papers (`paper` keys): `cold-press`, `hot-press`, `washi`, `xuan`, `newsprint`, `canvas`, all made by code.

A part of kind `accessory` with several colours (a basket of vegetables, a badge) is read as one layer per colour, so
a wash or a block does not paint it as one blob.

The checks (references/checks.md) run on the cel finish these engines start from, where a part map's mistakes show; the
result says `"on": "the cel base"`. On the engine's own result only the look checks O7 to O9 run (a skin printed another colour, a box round the features, mottled darks): look at the result itself for the rest.

## Measured against the real techniques

The woodblock and wash engines were compared with museum examples (Cleveland Museum of Art, CC0). The numbers were taken
at one height (900 px) by the same script, and only from the scans; the scans are in nothing shipped.

- **Woodblock**: five Edo prints.
  - The paper matched: washi at L 89–94, b* 6–9.
  - The flat share matched (0.48 against 0.47–0.58).
  - The grain matched (2.2).
  - The sumi did not. Its darkest 2 % measure L 18.6–26.4 in the prints but went to L 4 here, blocks printing over each other. The sumi is now L 22, and stacked blocks saturate at it.
- **Watercolour**: five 19th–20th-century watercolours.
  - Edge darkening is subtle at this scale: the median edge was 0.24 L lighter than the inside. The engine's default was +0.9 L above its own cel base, now about +0.5.
  - The darkest values lie near L 19 against 14 here; washes now saturate at L 20.
  - Chroma and the share of paper depend on the subject and the paper's age, and were not matched.
- **Ink**: five ink paintings (the central area; the scroll mounts left out). Their darkest ink lies at L 28–61, darkened and faded by age. Ours went to L 6 where lines crossed washes; it now saturates at its 焦 tone.

## Layers over any engine (`post`)

A style may list layers laid over its result, in order:

| op | keys | what it does |
|---|---|---|
| `relight` | `hour` (`night`, `sunset`, `dusk`, `film-night`), or `key` and `ambient` (linear RGB), `light` (direction), `floor`, `floor_amount`, `chroma` (a factor on every colour after the light), `chroma_cap`, `rim` | the colours relit for another hour: each colour read as a surface under the day's white light, then lit by the hour's key light where the finish had it lit and by its ambient light everywhere |
| `paper` | `kind`, `strength`, `tooth` | the sheet's colour through the light paint, its tooth catching the light |
| `grain` | `amount`, `size` (u), `shared` | film grain in density, strongest in the middle tones |
| `halation` | `threshold`, `radius` (u), `amount`, `tint` | the warm glow film gives round its brightest areas |
| `soften` | `radius` (u), `amount` | a lens's slight softness |
| `curve` | `lift`, `gain`, `gamma` (each a number or [r, g, b]) | a tone curve per channel: a film stock's lifted blacks and colour |
| `focus` | `at` (`face`, or [x, y] as fractions of the figure's box), `sharp` (u), `depth` (u), `radius` (u), `hot` | a lens's depth of field inside the figure: sharp round the focus, softening with distance to a disc `radius` wide, the brightest lights opening into discs (bokeh); for a close-up or a reaching hand. A scene's depth of field, with the background, belongs to `scripts/composite.py` (references/compositing.md) |
| `bokashi` | `colour` (Lab, default Prussian blue), `depth`, `reach` (share of the sky's height), `horizon` (Lab), `horizon_depth`, `horizon_reach` | scenes: a woodblock print's sky, the top wiped down from a deep pigment to nothing (一文字ぼかし), optionally a second gradation rising from the horizon (a sunset's red) |
| `mist` | `amount`, `bands`, `paper`, `interior_below` (0.04), `night_below` (45), `night_top` (52), `night_horizon` (72) | scenes: an ink painting's distance, the sky left as paper, the far hills faded toward it, everything fading with height, soft bands of mist where a far plane meets a nearer one (留白、遠近). The mist k (the distance times `amount`, plus the bands) is laid at 1 − (1 − k)², so it thickens fast with distance: `amount` 0.75 leaves a day sky 0.94 paper. An interior (sky under `interior_below` of the picture) does not fade with height. A night sky (median L under `night_below`) is washed in a pale ink, L `night_top` at the top to `night_horizon` at the horizon, the moon left as paper and the wash lightening round it (烘雲托月) |
| `wet_sky` | `blooms`, `clouds` | scenes: a watercolour sky in one wet-in-wet gradation from its top colour to a paler horizon, varied in soft blooms, the clouds left as paper |

The scene layers read the kinds of a scene's subject (`sky`, `far`, ...; scripts/scene_subject.py) and do nothing on a figure.

`scripts/refinish.py --hour night` adds a relight to any style that keeps the picture's size. The pixel, sticker and neon engines change it, so they take no post layers and refuse `--hour`. The checks look at the result before its layers.

The hours are two kinds of night. `night` is a TV colour designer's night model (夜色指定): everything darker and navy, a cool rim light. `film-night` is the night grade of theatrical anime: the figure stays light (skin about L 75 to 85) and loses most of its colour (skin chroma 4 to 7 against 15 to 25 by day), a warm lantern key and a cool sky ambient, so the shadows turn mauve-grey.

## Writing a new style

Start from the bundled style nearest to the target, change one section at a time, and run it on a test subject at full size. To match a reference, measure it first: references/replicating-a-style.md.
