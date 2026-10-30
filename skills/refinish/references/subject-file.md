# Subject files

A subject file describes one picture: where its parts are and which features are kept as drawn. The style says how to paint; the subject says what is there. Paths are relative to the subject file.

```json
{
 "format": "refinish-subject/1",
 "image": "image.png",
 "upscaled": 2,
 "families": {"navy": [[300, 100], [250, 400]], "skin": [[380, 395], [132, 445]]},
 "parts": [
  {"name": "hair", "family": "navy", "kind": "hair", "only_placed": true, "poly": [[0, 0], [966, 0], [966, 1420], [0, 1420]]},
  {"name": "skirt", "family": "navy", "kind": "cloth-dark", "poly": [[30, 1540], [705, 1140], [748, 1825], [30, 1825]]},
  {"name": "skin", "family": "skin", "kind": "skin"}
 ],
 "protect": [{"name": "left eye", "box": [312, 286, 378, 356]}, {"name": "mouth", "box": [366, 366, 422, 398], "de": 6}],
 "focal": [{"name": "face", "centre": [395, 345], "radii": [125, 135], "strength": 1.0}],
 "blush": [[340, 380, 26, 12]],
 "rules": {"tights": {"scale": 6.0}}
}
```

| key | meaning |
|---|---|
| `image` | the picture, cut out (RGBA) for figures; prepare it with `scripts/prep.py` (crop, enlarge) |
| `upscaled` | how many times the picture was enlarged: the line finder looks that many times wider |
| `head_px` | the head's height (crown to chin) in pixels, for a figure the frame cuts off (a bust, a reference still): the unit is then taken as seven heads, not the visible height, so a close-up and a full figure are measured alike |
| `families` | colour families: a few sample points each, covering its lit and its shaded tones |
| `parts` | `name`, `family`, `kind` (references/style-format.md), and where the part may be: `poly` or `polys`; `only_placed` keeps a family's pixels outside the polygon from going to that part; `exclusive` gives the part every pixel inside its polygons whatever their colour (a dark iris the colour of the dark hair round it: draw the polygon tightly round the iris) |
| `protect` | boxes round the eyes and the mouth: inside, everything not skin is kept as drawn; `de` lowers the colour step for faint features (a closed smile: 6) |
| `focal` | ellipses where detail matters most (the face, a raised hand): more lines kept, finer paint |
| `blush` | [x, y, rx, ry] spots for the style's blush |
| `rules` | per part name, any shading key, overriding the style for this picture; the place for a character's own colour model (`base_lab`, `shadow_lab`, `deep_lab`, `highlight.colour_lab`), which belongs to the character, not to the style, and for `"deblotch": 4` on a part that came out in blotches |
| `follow` | `drawn` or `form` for every part of this picture, overriding the style |

## Parts found automatically, named by whoever looks

Most pictures need no hand-placed samples. The reviewer (the agent running the skill) says what is there; the code finds exactly which pixels it is:

1. `scripts/auto_parts.py image.png subject.json --upscaled 2` writes a draft:
   - the areas the source's lines enclose, as a region map (`<subject>.regions.png`);
   - the face found by its eyes, the eyes and the mouth boxed, the hair grown from round the face, the skin, and the rest grouped by colour;
   - three review pictures, each with a grid in the picture's pixels:
     - `<subject>.auto.jpg`: every part in false colour, every region numbered;
     - `<subject>.face.jpg`: the face enlarged;
     - `<subject>.sheet.jpg`: every part on its own, in its own colours.
2. Look at the picture itself (`scripts/zoom.py image.png 0,0,W,H all.jpg --step 100`) and list its materials: every material that should take its own colours is a part. Watch for the easy ones to miss:
   - the white frills of a petticoat under a coloured skirt;
   - a lining, and the inside of an open jacket in shadow: it belongs to the jacket, not to what is under it;
   - the shaded underside of a metal plate;
   - a print;
   - ribbons;
   - things held (a tray, a cup, a weapon).
3. Write a hints file naming **every** part, with:
   - **Points:** one or two per part. For a part with strong shading (metal, a painting), put one on its lit side and one in its darkest shade: the darkest shade of a steel plate is as dark as cloth beside it, and is given to the part whose points are nearest in colour.
     - Check every point's colour in `hints.py check`. On a part of several colours (a print, a knit, a device) the check cannot say which colours are wrong. A point on the shadow where two parts meet pulls that shadow into the part it names.
   - **Boxes:** a rough box round each piece of the part. Nothing outside a part's boxes can be that part. The boxes are a hard limit, so draw them generously:
     - **Too small:** a leg goes on under a skirt's hem, a wrist below a sleeve, a neckline down past the collar. Draw the box past the place where the part disappears.
     - **Too wide:** a box round an apron also covers the sleeve beside it, and the sleeve's shadow goes to the apron. A part that is not a rectangle (an apron's bib and skirt, long hair on both sides of a body) gets several boxes that follow its shape.
   - **Eyes and mouth:** rough boxes round them.
   - **Getting the points:** reading a region's number off `<subject>.auto.jpg` and turning it into a point (`scripts/hints.py points subject.json 12 40 77`) is surer than reading coordinates. When reading coordinates off a grid, zoom into a crowded place first, then let `scripts/hints.py pick image.png x0,y0,x1,y1 --like x,y` move the point into the middle of its colour's largest patch in that box (with no `--like`, it gives a point for each of the box's main colours).
   - **Before running:** `scripts/hints.py check hints.json subject.json` shows where each point lands: its colour, the part the draft gives it, and whether it lies outside the figure or its part's boxes. Measured on new pictures, about three points in ten read off a grid landed on the background or on the thing beside the part.
4. Run `auto_parts.py` again with `--hints hints.json`, then go through what it gives:
   - **Every doubt.** They name the colour and the share of what looks wrong. Three kinds:
     - "part 'dress' (pink) holds white regions 968, 996 (1.9 % of the figure)";
     - "part 'skin' seems to go on past the top edge of its box": a box drawn too small;
     - "region 9 holds two colours far apart (navy and brown, 61.1 % of the figure)": a gap in a line let two materials run together into one region; a point on each cuts them apart.
   - **The parts sheet.** On it, a material mixed into the wrong part shows at once, where false colours may hide it.
   - **A finish and its checks.** Finish the picture in the style it is meant for (`scripts/refinish.py`) and treat every FAIL its checks report as one more doubt. M1 in particular names a patch with a neighbouring part's colour, the commonest result of a box drawn too small or a point on the wrong material.
   - **Fix and run again.** Add a point or a part where something is wrong, and run again. Two rounds settle most pictures.
   - **When a person reviews it.** Show the parts sheet and ask for one sentence about what is wrong, in their words ("the bow on the apron is part of the skirt", "her hair over the cardigan is cut straight"). Do not ask them for boxes or points: turn the sentence into them yourself (a point on the bow and a part for it; points on both sides of the hair's edge), run again, and show the sheet again. Measured on new pictures, an agent's own points went wrong far more often than its reading of a sentence about what to fix.

Measured on 20 new pictures (two batches, the code frozen before each was opened): all 10 clean TV-cel characters came out right within two rounds. Of the 10 hard ones, 5 did:
- a semi-realistic painting;
- dense patterns;
- white on white;
- black on black;
- a figure hung with gear.

The misses were boxes and points, not the code's cuts:
- a box drawn too small, or a single box round a diagonal or ragged thing;
- a point on the shadow where two materials meet;
- one dark point in a black area with no lines inside it, which takes the whole area.

For the hard cases, look at the parts sheet with particular care, and for black on black name fewer, larger parts than you would like.

```json
{
 "complete": true,
 "eyes": [[297, 318, 369, 353], [419, 266, 496, 312]],
 "mouth": [398, 381, 443, 398],
 "parts": [
  {"name": "hair", "kind": "hair", "at": [[300, 100], [870, 1000], [250, 1150]]},
  {"name": "skirt", "kind": "cloth-dark", "at": [[450, 1500]]},
  {"name": "headphones", "kind": "accessory", "at": [[360, 574], [434, 571], [424, 472]]},
  {"name": "buttons", "kind": "accessory", "at": [[495, 1130]], "within": [440, 1080, 560, 1640]}
 ]
}
```

How the hints are read:
- **Eyes and mouth boxes** snap to the holes the eyes and the mouth leave in the skin. A box is the hole found and the box given together, the hole held near the box: a hole may be only the upper half of an eye or one end of a smile, while the box drawn holds all of it; and a beard round a mouth is a hole too, which the box keeps out. A rough box drawn by eye is enough.
- **Points grow into their parts.** Each point's part spreads from the region under it, all parts at once, the way a colourist's bucket fills line art (scribble colouring: Sýkora et al., *LazyBrush*, 2009). Navy hair and a navy skirt, pointed at apart, stay apart where they meet.
- **Unclosed outlines are cut by the points.** Where the lines fail to close off a part (a print on a shirt, a hair clip, a coat and trousers of one navy in a painting with few lines), the points inside one region split it by a watershed from markers (Beucher & Meyer 1993, computed as an image foresting transform: Falcão et al. 2004). The parts flood the region at once, and the boundary falls on the strongest colour edge between them, however soft the shading. What is far in colour from the points that flooded it becomes a region of its own; so does what is far from the points of the only part pointed at in a region (a white collar flap holding the stripe pointed at).
  - An edge with one part's colours on both sides (its lit and its shaded tone, each clearly nearest that part's points) is that part's shading and counts for little, so a faint line between dark trousers and dark shoes still bounds them where it is no stronger than the trousers' own shadow. Point at both tones of a strongly shaded part.
  - The line art, the figure's own outline included, goes with the fill nearest it, not with the part nearest its dark colour: measured on 28 pictures, a dark part's flood had run along the lines round its neighbours (a ball's seams taken by the hand holding it, a trouser leg's outline by its buttons).
- **`boxes` cut a part out of a box.** A part may have rough boxes round it (`"boxes": [[x0, y0, x1, y1], ...]`, one per piece: two shoes, two sleeves). The part is cut out inside them by GrabCut (Rother, Kolmogorov & Blake 2004). Nothing outside a part's boxes can be it.
  - **The limit is kept last.** After every other step, each piece of a part lying outside its boxes goes to the part whose points are nearest in colour, among those whose boxes hold the piece (or that have no boxes). A piece no other part may hold stays.
  - **On a low-contrast picture this matters most.** A pale picture's lines enclose huge regions running across hair and dress alike, and only the boxes keep them apart.
  - **How the cut starts.** Each pixel goes to the part whose points are nearer in colour, among the parts that may be there (inside their boxes). A colour clearly another part's (nearer by more than 10) is never this one, so a soft painting's smoothness cannot pull it in.
  - **Lines are surer than cuts.** A region its drawn lines enclose that holds a point is that point's part, whatever the cuts say. A lit cheek inside the face's outline stays the skin's even where the hair's cut reached. The one exception is what another part's cut took that is clearly nearer in colour to that part's points: a cream bodice behind a forearm, where the line between them was missed, goes to the dress.
  - This is what keeps parts apart in the hard cases. In a painting with few lines, a coat boxed apart from the face is not taken by the skin. In a dense print, the skirt boxed apart from the arms keeps its pale flowers.
  - Measured on new pictures: a semi-realistic trench coat, a cream dress with small flowers, and a white dress on a pale girl were cut wrong by points alone, and came out right with boxes.
  - Give a box to every part, a little larger than the part. Box a V-shaped part (a turtleneck between lapels) all the same: the cut starts from the points' colours, not from the box, so the lapels inside the box stay with the coat.
  - Two parts of exactly one colour (a white ribbon on white hair) are told apart only by the lines between them. When the lines are too faint, name them as one part.
- **`within` selects a scattered pattern.** It takes every region of the point's colour inside the box: the motifs of a print, a row of buttons.
- **`complete: true`** means the parts named are all there is. What no point reached joins a named part by seeded region growing (Adams & Bischof 1994): of all the unclaimed regions touching a part, the one nearest in colour to that part's points joins first. A region that touches nothing of its colour goes to the named part of its colour wherever that is (a sleeve cut off from its shirt by a collar's stripe). The draft's own parts are dropped, except the eyes and the mouth found in the face.
- **Doubts are printed** in seven cases:
  - the colours disagree with a name ("region 412 reads as skin but was named 'skirt'");
  - a part holds a share of another colour ("part 'dress' (pink) holds white regions …");
  - a part runs into the edge of its box and its colour goes on past it ("part 'skin' seems to go on past the top edge of its box …");
  - two named parts of nearly one colour touch ("parts 'hair' … are nearly the same colour"): no colour tells them apart, so their border follows the boxes and the lines, and a box's straight edge can cut a lock of hair; look along that border, and give points on both sides of it where it goes wrong;
  - no eyes were read in the face (glasses over them, eyes closed) and the eye boxes given are used as they are: check them on the face sheet;
  - a part's points reached nothing;
  - a point lies outside the figure.
- **Glasses.** A frame round the eyes can hide them from the face reading. Give the eye boxes anyway: when the face is found but no eye in it, the boxes given are the eyes, and the frame inside them is kept as drawn with the eye.

**What the points cannot do.** A densely patterned garment (a kimono of cranes and clouds painted in soft gradients) is not worth splitting motif by motif. Name the garment as one part and give it the rule `"model": "regions"`, so each region its lines enclose is painted flat in its own colour.

With `--like other_subject.json` the names and kinds of another picture of the same character are reused, so a set gets the same parts.

A part that owns regions keeps them in its `regions` list. To move a region, move its number. A polygon added to such a part takes every pixel inside it.

## When the parts will not come right

Two rounds of hints settle most clean cel pictures. When a third round would only move the same mistakes around, change the approach instead of the points. Try these in order:

1. **Ask for one sentence.** Show the person the parts sheet and ask what is wrong, in their words (step 4 above). A sentence about the picture is surer than another round of points read off a grid.
2. **Name fewer, larger parts.** Black on black, white on white and two materials of one colour are told apart only by the lines between them. Where those lines are faint, one part painted from one colour model looks better than two that trade pixels along a guessed border.
3. **One part for a dense pattern.** A garment of many small motifs is one part with the rule `"model": "regions"`, so each region its lines enclose keeps its own flat colour.
4. **Eyes the face reading missed.** When the draft reads no eyes (glasses, closed eyes, a stylised eye), the eye boxes given are used as they are, so draw them tightly round each eye. An iris that still lands in the skin or the hair moves with their colours; check P2 says so. Give it a part of its own, of kind `eyes`, with a point on the iris and a tight box.
5. **Finish only the parts that are right.** A recipe with `"base": "source"` re-finishes the parts its layers name and leaves the rest of the picture as drawn ([recipes.md](recipes.md)).
6. **Use a finish that needs no parts.** The de-AI and duotone styles run on the draft as it is.
7. **Start from a source that can be split.** Soft airbrushed shading and an outline missing on the lit side are made at generation, and no hint repairs them. `scripts/check_input.py` grades both. Where the picture can be generated again, [source-spec.md](source-spec.md) says what to ask for.

Tell the person which of these you used and why. A part merged, or left as drawn, is a choice they should know about.

## How each pixel finds its part (hand-made subjects)

1. Each pixel goes to the nearest colour family **among the families with a part allowed where it lies** (a polygon, or anywhere for a part without one). A lock of hair beside the cheek may be nearest in colour to the tights; the tights may not be there, so it goes to the hair instead of falling through to the skin.
2. Each pixel then takes the family most of its neighbourhood has (speckle and lines join the region around them).
3. Placed parts take their family's pixels inside their polygons; unplaced parts take the rest of their family.
4. What is left goes to a part allowed there and present nearby whose samples are nearest in colour, and finally to the nearest part in space.

## Writing one

1. `scripts/prep.py SRC.png image.png --grid` writes the picture and a copy with a 100 px grid.
2. Place two to five samples per family on clean pixels of its lit and its shaded tones. Print the colours under the samples and check each one (a sample on a line or on the wrong part is the commonest mistake).
3. Give a polygon only to parts that share a family with another part (navy hair and a navy skirt; black tights and black shoes split by colour when their blacks differ).
4. Box the eyes and the mouth tightly; measure their place on a fine grid, not by eye on the whole picture.
5. `scripts/parts.py subject.json` builds the part map and lists likely mistakes ("misfits": a dark lock labelled skin, a light patch labelled hair). Fix them by adding a sample or tightening a polygon, and run it again until none is left. Look at the review picture at full size round the face and the hands.

A small accessory of several colours (headphones, a badge) is a part of kind `accessory`, kept as drawn by the bundled styles; a dark detail inside it whose colour no family covers (a speaker mesh) gets a family and a part of its own.

For a style that changes the colour model (night to day, a muted source to a rich one), the eyes need parts of their own, kind `eyes`: the whites (often only a few steps from the skin's colour, so the protected boxes' colour test misses them and they would be painted as skin) and the irises (`exclusive`, when they are as dark as the hair). Pure black (shadow masses, black prints) is a family and a part of kind `accessory` of its own, kept as drawn.

## Scenes

A background or a landscape is a subject too: `scripts/scene_subject.py IMAGE.png SUBJECT.json`.
- It looks for no face.
- It does not outline the picture's frame.
- Its parts are found by colour, not by lines (a painted background closes few areas with lines): the colours are flattened, grouped into families, and each family's connected areas become its regions.
- Each area gets a guessed kind: `sky` (the clouds in it too), `far` (blue with distance), `water`, `foliage`, `ground`, `wood`, `roof`, `stone`, `wall`, `cloth`.
- Two guesses are corrected by shape and colour: a tall narrow greyish area reaching the top (under 8 % of the width, over 25 % of the height) is a pillar or a door frame, `stone` or `wall`, not sky; water needs some colour (chroma over 14), so night-tinted stone is not water.
- A scene with almost no sky (under 4 %) is read as an interior: the ink styles lay its large areas in the lighter inks, and the mist does not fade it with height.

The kinds steer only the scene layers (`bokashi`, `mist`, `wet_sky`; references/style-format.md) and these few choices. A wrong guess paints that area like any other; fix a kind in the file when it matters.

