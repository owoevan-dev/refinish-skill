# Choosing a card's colours

The card's colours go onto a drawing made for other ones. What follows is how an anime colour designer chooses a colour model, and what the tests of this skill showed goes wrong when a recolour ignores it.

## A colour model, not a colour

A colour designer (色彩設計) gives each material of a character a set of colours, the colour model (色指定): the lit colour (ノーマル), the shadow (1号影), often a second shadow (2号影) for the deepest folds, and a highlight. The shadow is a colour of its own, chosen for the scene's light, not the base darkened ([CG World on 『アニメーションの色彩設計から学ぶ 色彩&配色テクニック』](https://cgworld.jp/news/book/1906-genkobook19124.html)). A card that gives only bases gets its shadows by that practice (the rule in [palette-format.md](palette-format.md)); a card that gives shadows gets them exactly.

## Lightness before hue

A figure reads by lightness before it reads by hue. Check the card on its board for:
- **Touching parts a step apart.** Hair against the face, the coat against the shirt, the skirt against the legs: about 15–20 of CIELAB L* between them, or the two read as one shape, line or no line.
- **The silhouette against the background** the picture will stand on.
- **A dark part made light.** The drawing's dark marks inside it (strands, creases drawn as lines) show far more on the light colour than they did on the dark one. That is the drawing; a shadow with a little more grey in it keeps those marks calmer.
- **A light part made dark.** Its shadow has little room left below it: a near-black part gets a second shadow only a few steps down, and its lines are drawn darker still.

## Shadows

- **Most materials: cooler.** Under warm light a shadow is lit by the sky, so it leans blue (James Gurney, *Color and Light*, 2010, the chapters on shadows and skylight). The derived shadow turns its hue toward blue-violet, at most 18°, and gains a little chroma: a colour model's shadow is richer than its base, not greyer.
- **Skin: warmer.** Light scattered under the skin reddens and saturates its shadow edge (Gurney, the same book). Skin's shadow turns toward red, at most 10°, a smaller step down.
- **Whites and greys: tinted.** A white shirt's shadow is lavender-grey, not grey: a near-neutral base gets a little chroma at the cool hue.
- **A scene's own light** (night, sunset) belongs to the style or to a relight, not to the card: give the character's own colours, as they are by day.

## Lights

A highlight is the light's colour on the material, not white. On dark hair it is a mid tone (the derived one lies 0.4 of the way from the base to white); on gloss (patent leather, metal) it is near white: give it on the card.

## Area: main, sub and accent

A common rule of thumb in Japanese colour coordination (配色の黄金比) puts about 70% of the area in one colour, 25% in a second and 5% in an accent. The card's roles follow area the same way: the largest garment takes `main`, the next `sub`, the small things (a ribbon, buttons, a clip) `accent`. A strong colour as the main one tires the eye; it carries best as the accent.

## Eyes

- The iris carries much of a character's identity. Choose it against the skin and the hair: an iris the hair's colour disappears under the fringe.
- The pupil stays dark and the catchlights white: the iris's colour runs from the iris's own darkest to its lightest.
- Both eyes take one colour; the check RC3 reports two eyes that came out unlike.

## What one card cannot do yet

- **Several colours in one part** (streaks in the hair, a gradient from roots to tips, a pattern's own colours): each part takes one colour model. Streaks that are parts of their own (hints, in the Refinish skill's subject file) take their own colours.
- **Colours the drawing has no tones for**: the shading stays where the source drew it, so a colour that wants another light (a glow, a rim light) needs a relight.

## Sources

- Colour design: CG World's note on 『アニメーションの色彩設計から学ぶ 色彩&配色テクニック』 (https://cgworld.jp/news/book/1906-genkobook19124.html).
- Compositing to a colour design, a gradient map from lightness to the designed colours, light in linear light: an anime compositor's notes (https://scrapbox.io/aodaruma/).
- Light and shadow colour: James Gurney, *Color and Light: A Guide for the Realist Painter*, 2010.
- Oklab and OkLCh, the colour space every derivation runs in: Björn Ottosson, "A perceptual color space for image processing", 2020 (https://bottosson.github.io/posts/oklab/).
- Gamut mapping that keeps lightness and hue: CSS Color Module Level 4, §13–14 (https://www.w3.org/TR/css-color-4/).
- The checks' colour difference: Sharma, Wu and Dalal, "The CIEDE2000 color-difference formula", Color Research & Application 30(1), 2005.
- Monotonic lightness, smooth falloff and gamut mapping in recolouring: Chang, Fried, Liu, DiVerdi and Finkelstein, "Palette-based Photo Recoloring", SIGGRAPH 2015.
