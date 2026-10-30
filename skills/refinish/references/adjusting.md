# Adjusting a finish to the picture

The bundled styles work on most pictures, but no setting is right for every picture. When a result shows a problem,
change the settings for this picture, not the scripts:
- one part's rule in the subject, first;
- the style, after that.

This page lists the problems seen most often. For each it says what it looks like, why it happens, and which setting
moves it. The checks O7 to O9 (checks.md) point at the first four.

## The loop

1. **Find the symptom.**
   - Look at the result at full size beside the source, and at the face and the hands at 1:1 (`scripts/zoom.py`).
   - Read the check's findings.
2. **Change one setting**, the narrowest first. The places, narrowest first:
   - a part's rule: the subject's `"rules": {"<part>": {...}}`, merged over the style's rule for that kind;
   - the whole picture: the subject's `"follow"`;
   - a copy of the style: style-format.md lists every key, and `scripts/tweak_style.py` takes words.
3. **Render again** and compare the same crops, before and after.
4. **Stop** when the symptom is gone and nothing new has appeared. Tell the user what you changed and why.
5. **For a batch** (a set of sprites, a cast):
   - settle a setting on two or three pictures;
   - then check it on pictures you did not tune it on. A setting that only works on the pictures it was tuned on is overfitted.

**When to stop and say so:** if two or three changes do not keep the character's skin, face or a key part of the design, the style does not suit this picture. Say so, and offer another style.

## Skin painted another colour (O7)

**What it looks like:** a brown skin printed pale, or a light skin printed far darker than the rest of the figure.

**Why:** some styles have a convention for skin:
- the woodblock prints leave a light skin near the paper;
- manga leaves a light skin as paper;
- pop art prints skin in red and yellow dots.

Applied to every skin, such a convention would change who the character is. The engines keep a darker skin's own value. These settings set where the convention stops:

| style | setting | default | what it does |
|---|---|---|---|
| woodblock (both) | `woodblock.pale_above` | 74 | skins lighter than this (L) are printed near the paper; darker ones blend to their own value over the next 14 |
| woodblock | `woodblock.skin` | 0.06 | how much beni a light skin carries |
| manga-screentone | `tone.skin_paper_below` | 0.35 | skins lighter than this density stay paper; darker ones take a dot tone |
| manga-screentone | `tone.skin_tone_scale` | 0.65 | a darker skin's tone, as a share of its density |
| pop-art-dots | `pop.spot_above` | 10 | how far (delta E) the nearest ink overprint may be before a skin takes a spot ink of its own colour |

**Never deliver** a result that changes a character's skin tone.

## A box round the eyes or the mouth (O8)

**What it looks like:** a rectangle of another tone round an eye or the mouth.

**Why:** inside a protected box the features are kept as drawn, or inked from the source. Where the skin round them is repainted differently, the box's straight edge shows. The engines keep only the features' darks, measured against the face's own skin, and leave hair and cloth that cross the box to their parts.

**What to change:**
- **A tighter box.** Hug the eye and the mouth, not the brow and the cheek.
- **The box's `de`**, its colour step. A larger step keeps less as a feature; a smaller one keeps more.
- **Labels inside the box.** A lock of hair inside an eye's box must be labelled hair.

## Frayed shadow edges and flecks

**What it looks like:** a shadow edge that frays into flecks, on a face or a garment. It happens where the source's shading is soft and noisy, as an airbrushed AI picture's often is.

**Why:** a flat-tone cut through a shallow, noisy gradient follows the noise. The gentler the gradient, the farther the noise moves the cut.

**What to change:**

| setting | where | what it does |
|---|---|---|
| `"deblotch": 3` (u; 3 to 10) | the part's rule in the subject | the part's shading read at a broader scale before the cut |
| `"auto_deblotch": 18` | the style's `shading`, or a part's rule | the broader reading only for parts whose own cut comes out ragged (`core.cut_raggedness` above 18) and whose two tones are close (less than 25 L apart). It tries 3, 6 and 10 u and takes the smallest that is clean. The shadow keeps the share of the part it had. |
| `"follow": "form"` | the subject | every part's shadow is read as one clean shape at the scale of its forms |

**Watch out:**
- The broader reading rounds small drawn shadows, and it can merge a printed pattern into its cloth. Leave it off patterned parts and off hair.
- Look at 1:1 after the change.
- On the test pictures it cleaned a painted leather jacket and a soft silk dress, but on the jacket the large shadow shape crossed the belts.
- The lasting fix is a source generated to the spec (source-spec.md).

## Dark areas broken into patches (O9)

**What it looks like:** a black coat in camouflage patches.

**Why:** a texture or a wash's drift. A few points of density are many points of lightness near black. The engines fade their textures on dark areas. A dark part that still mottles takes calmer settings:

| style | settings (lower is calmer) |
|---|---|
| watercolour, ink wash | `wash.flow` 0.12, `wash.granulation` 0.18, `wash.dispersion` 0.05 |
| charcoal, soft pastel | `drawing.tooth` 0.6; a wider `drawing.hatch` (u) |
| woodblock | `woodblock.grain` 0.07 |
| screen print | `print.uneven` 0.12 |

## A face that cannot be read

| style | what to change |
|---|---|
| pop-art-dots | A smaller `pop.cell` (9 u) for a small face. The eyes and the mouth are painted flat, without dots, so check that the protect boxes cover them. |
| neon-sign | On the face the tubes are paler, thinner and glow less (`neon.face_pale` 0.55, `face_thin` 0.4, `face_dim` 0.6). A larger `neon.min_line` drops short lines. |
| charcoal | The skin is blended as with a stump. A lower `drawing.strength` gives a lighter face. |
| pixel styles | A sprite's face is a few pixels by design. Use `pixel-portrait` for a larger one. |

## A thin part lost or in the wrong colour

**What it looks like:** a cord, a strap or an earring that vanishes, or comes out in the colour of its own outline.

**Why:**
- a cut edge smoothed wider than the part (paper cut);
- a thin part's colour read off its outline.

The paper cut limits each piece's smoothing to about half its width. It fills any sliver no sheet covers inside the drawing with the cel base's colour; what the smoothed outer edge closes beyond the drawing is cut from the sheet beside it, and the eyes lie on the face's paper as drawn, with no sheet of their own under them. Paper cut and woodblock read each part's colour off its fill.

**What to change:**
- a smaller `papercut.simplify`;
- the part given a name and kind of its own in the subject (a cord as `accessory`).

## A costume printed in the wrong ink

**What it looks like:** a beige coat printed pink (screen print, two-colour print, riso).

**Why:** a print has few inks. Each colour ink is the colour of the largest part it prints. A smaller part takes the nearest ink.

**What to change:**
- more inks: `print.inks` 5 or 6;
- or the inks given outright, as Lab colours: `"inks": [[L, a, b], ...]`, the first one the key.

## Blacks turned grey or brown (paint styles)

The paint engine keeps a mass of pure black as black. A dark garment that still lifts is a dark grey in the source. Use the style's `palette.contrast` and `palette.lift`.

## Wrong colours in every style

This is the part map, not the style. See checks.md (P1, M1, O1, O5) and subject-file.md.
