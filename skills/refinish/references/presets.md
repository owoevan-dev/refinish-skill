# The bundled styles

Every style in `styles/` by family:
- what it needs from the subject;
- what to ask of the source (pre-production; references/source-spec.md has the full cel spec);
- where it falls short.

Styles are named by technique, never by a work or an artist.

**Parts?** says whether the style paints by parts:
- **yes** needs a subject file with parts (scripts/auto_parts.py, with hints for best results; references/subject-file.md);
- **no** runs on the automatic draft with no hints at all.

## Cel (anime paint)

| style | look | parts? | pre-production | limits |
|---|---|---|---|---|
| `tv-cel` | TV anime cel: two hard tones, coloured trace lines, a closed outline | yes | the cel source spec, level 2 | a soft painting blotches; generate to the spec or use a paint style |
| `heavy-cel` | dense three-tone cel: a second shadow, crisp hair light, the fringe's cast shadow, heavier ink lines | yes | level 2; a key light from one side so the second shadow has somewhere to go | busy designs get busy |
| `bold-ink-cel` | bold TV look: black ink lines kept as drawn, clothes brought to a vivid chroma target | yes | the line art in solid black already; level 2 shading | pale garments are held back on purpose (no neon) |
| `film-everyday-cel` | a theatrical film's everyday look: a soft turn into shadow, muted palette, warm dark lines, a whisper of grain | yes | level 2; muted local colours help | — |
| `film-everyday-night-cel` | the same at night: the figure light but nearly colourless, warm key, mauve-grey shadows (fitted to measurements of night stills) | yes | generate in **day** colours under neutral light; the night is made here | a scene's own coloured lights (lanterns) are not added: composite them |
| `pastel-film-cel` | high-key pastel film look: lifted values, softer contrast | yes | light designs | dark designs lose their weight |
| `cel-90s` | painted cels photographed on film: cool violet shadows, a wandering trace line, lifted blacks, halation, grain | yes | level 2 | — |
| `tv-cel-night`, `tv-cel-sunset` | the TV cel relit for night (navy, a cool rim) or sunset (warm key, violet shadows) | yes | generate in day colours under neutral light | — |

## De-AI

| style | look | parts? | pre-production | limits |
|---|---|---|---|---|
| `deai-light` | the picture's own colours and lines; noise and airbrush gradients pulled half-way to clean tones | no | none | — |
| `deai-strong` | every area in clean flat tones, crisp lines in a dark shade of their own colour, a closed outline | no | clean line art helps most | hair drawn as a mass of fine glints can keep pale flecks; a fringe's tips can blotch (validation: 19 of 21 new pictures passed, 21 of 21 for light) |

This is finishing quality: a cleaner, more deliberate finish. It is never a way to hide where a picture came from.
references/legal-and-disclosure.md says what to disclose.

## Duotone and limited inks

| style | look | parts? | pre-production | limits |
|---|---|---|---|---|
| `duotone-auto` | the picture's own two colours: one median colour and its shadow over the drawing | no | — | the colours change completely; the drawing stays |
| `duotone-navy` | a gradient map, navy to cream | no | a strong value structure | — |
| `two-colour-print` | a magazine's black-and-red page: two plates screened at 45 and 75 degrees on newsprint | no | — | a design with no red reads as black and grey |
| `sepia` | a sepia-toned photograph's browns | no | — | — |
| `cyanotype` | Prussian blue on watercolour paper, contrasty | no | — | soft middle tones go to paper |
| `riso-pink-blue` | a two-drum risograph print: fluorescent pink and blue over each other, a fine grain, off register | no | — | ink colours are approximate (a swatch is itself one) |

## Painterly

| style | look | parts? | pre-production | limits |
|---|---|---|---|---|
| `watercolour` | transparent washes on cold-press paper: lights left as paper, glazed shadows, drying edges, granulation, blooms, a faint pencil line | yes | light, airy designs with clear lines | large black areas look heavy in a wash |
| `gouache` | opaque matte paint: brush masses, soft edges | yes | forms clear in the source | — |
| `thick-paint` | thick painterly strokes (厚塗り): the masses re-painted along the forms | yes | one key light | small accessories simplify |

## Print and line

| style | look | parts? | pre-production | limits |
|---|---|---|---|---|
| `manga-screentone` | black ink and dot tone on white: dark parts solid, light parts paper, the middle a tone by density; a light skin stays paper, a darker one takes a plain dot tone | yes | clean closed lines; each material of its own value | colour-only distinctions (two greys of equal value) merge |
| `genga-pencil` | an animator's key drawing: graphite lines on drawing paper, shadow edges in coloured pencil by the common convention | yes | clean line art; shadows drawn as shapes | the colour-pencil convention differs between studios: set the colours |
| `screenprint` | a four-ink screen print: spot inks (each the colour of the largest part it prints), dot tints at their own angles, off register, uneven ink | yes | bold shapes, a limited palette | fine detail drops out; a small part takes the nearest ink (more inks, or inks given outright: adjusting.md) |

## Special

| style | look | parts? | pre-production | limits |
|---|---|---|---|---|
| `ink-wash` | sumi-e: the five tones of ink, a dry-brush line, washes feathering into xuan paper | yes | value contrast between materials | colour is gone by design (one accent kind may be kept) |
| `ukiyo-e-woodblock` | an Edo colour woodblock print: key block in sumi, period pigments, bokashi shadows, wood grain, washi, off register; a light skin near the paper as in the prints, a darker one in its own value | yes | flat areas, clear outlines, few materials | gradients and many small details are lost; a colour between two period pigments takes the nearer (a teal goes blue) |
| `pop-art-dots` | comic-print pop art: heavy black lines, flat process inks (red, yellow, blue, black on white), every tint an even grid of Ben-Day dots, one dotted ink per tone; a tan or brown skin in a spot ink of its own colour; the eyes and mouth painted flat | yes | big flat shapes, a few strong colours | pale designs turn to dots everywhere; small features simplify; a small face needs a smaller `cell` |
| `neon-sign` | the line art redrawn as glowing glass tubes in the parts' own hues (greys and blacks burn white) on a dark ground, a white-hot core, a glow past the figure; the face in paler, finer tubes | yes | clean, continuous line art; distinct hues per material | the fills nearly vanish: the figure reads by its lines; **the picture grows** by the glow |
| `stained-glass` | pieces of coloured glass in lead: each tone area cut into glazier's pieces, every sheet a little different and lit from within, the line art painted on the glass (grisaille), skin painted on whole glass | yes | flat colour areas, clear lines | small parts become single pieces; a busy print is lost |
| `paper-cut` | layers of cut coloured paper: flat sheets per tone with clean, simplified cut edges (a thin part cut finer), a soft shadow under each sheet, the paper's fibre, no drawn lines | yes | big shapes, a few colours per material | a feature drawn only by a line (a chin over a neck of the same skin) disappears: there are no lines |
| `charcoal` | charcoal on cream paper: hatched tones pressed into the tooth, the darks laid flat, the skin blended as with a stump, a broken line, the lights lifted with white chalk | yes | clear values between materials | colour is gone by design |
| `soft-pastel` | soft pastel on toned paper: the parts' colours laid broad and finger-blended, the paper in the tooth's hollows | yes | mid-value, not too dark designs | very dark parts lose their detail; the paper's tone shifts the lightest colours a little |
| `sticker` | a die-cut sticker: the figure in TV cel on a white vinyl border cut along its outline (notches closed, corners rounded), a soft shadow, a faint sheen | yes | a clear silhouette | **the picture grows** by the border and the shadow (a recipe cannot mix it; composite it as it is) |

## Pixel

| style | look | parts? | pre-production | limits |
|---|---|---|---|---|
| `pixel-character` | a 96-pixel sprite: per-part ramps, a selective outline, hard alpha, the palette written beside it | yes | a strong silhouette, big shapes, a distinct colour per material | small accessories and the face simplify to a few pixels |
| `pixel-portrait` | a 192-pixel sprite: more colours, a dark outline, the drawn folds kept | yes | as above | — |

## Scenes

`scripts/scene_subject.py` makes a subject for a background: parts by colour, not by lines, and kinds such as sky, far, foliage and ground. It looks for no face.

- Every style runs on it.
- The `*-scene` styles add what the techniques do to a landscape.
- The kinds are guesses. They are surest on a daytime landscape. In a night scene, bluish stone may be read as sky; fix the kind in the subject file. Interiors with large near-black areas print heavy in woodblock.

| style | adds |
|---|---|
| `woodblock-scene` | a Prussian-blue bokashi wiped down from the top of the sky (一文字ぼかし) |
| `ink-wash-scene` | the sky left as paper, far hills faded, bands of mist between the planes (留白、遠近); a night sky washed in pale ink round the moon, which is left as paper (烘雲托月) |
| `watercolour-scene` | the sky in one wet-in-wet gradation with blooms, the clouds left as paper |

## Camera

The lens is not a style.
- Depth of field, bokeh, light wrap and the frame's grade are scripts/composite.py (references/compositing.md).
- A depth of field inside one figure is the `focus` post layer (references/style-format.md).
