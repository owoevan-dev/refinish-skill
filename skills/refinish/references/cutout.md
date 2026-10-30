# Cutting a figure out of a picture with a background

The figure styles need a cut-out. A figure generated on a transparent or plain background is still the best source
(source-spec.md). Most pictures, though, are a character drawn into a scene. `scripts/cutout.py` takes the figure out
of such a picture, so it can be finished and put back where it was, with the background finished on its own or left
as it is.

## How it works

`python scripts/cutout.py PICTURE.png OUTLINE.json OUT_DIR [--trimap TRIMAP.png]`

You draw a rough outline round the figure; the colours decide the exact edge.
- Inside the outline, three bands in, is sure figure.
- Outside it, one band out, is sure background.
- GrabCut (OpenCV) learns the colours of both, then cuts the zone between them along the strongest colour changes.

Everything is code and runs in seconds. There is no image model and nothing is generated.

It writes:
- `figure.png`: the cut-out, the picture's size and place;
- `background.png`: the picture with the figure's place filled from round it;
- `review.jpg`: your outline in cyan, the cut in magenta, the cut-out on green, and the doubts enlarged;
- `cutout.json`: the figure's box and the doubts.

## The outline file

```json
{"outline": [[[x, y], ...], [[x, y], ...]],
 "holes": [[[x, y], ...]],
 "band": 16,
 "bands": [{"box": [x0, y0, x1, y1], "band": 8}],
 "keep": [[x, y]],
 "drop": [[x, y]]}
```

**Outline.** One polygon round the figure, in the picture's pixels. Read them off `scripts/zoom.py` grids.
- Keep it **outside** the edge, within a band of it. Twenty to forty points follow a standing figure.
- Go round flying hair, a fluttering scarf and the fingers; round strands, never through them.
- Give each piece that goes with the figure its own small polygon if it stands apart: a held prop, a wing, a horn. A small polygon is sure figure halfway in, so draw it close.

**Holes.** A gap the outline has gone round is background inside the figure: the space between the legs, an arm's
loop, the inside of a handle. Draw each as a hole, inside the gap and within a band of its edges.
- Without a hole, a gap deeper than three bands is sure figure and stays in.
- A hole works even where the gap's colour is also the figure's (a purple sky behind purple hair).

**Band.** How wide the colours decide, in pixels either side of the outline. Its default of 16 suits a figure
1000 to 2000 px tall. `bands` changes it inside a box.

**Points.** `keep` and `drop` points make a small spot sure (a strand, a strap; a speck of sky between strands). Each also opens the other side's sure part round it:
- three bands round a drop point;
- two bands round a keep point.

A point never spreads by colour. A colour shared by the figure and the background is exactly what fools a magic wand: tried on a gap of dark wall between dark socks, the wand took the socks and the shoes with it.

## Reading the review

Look at the cut-out on green at full size, then at each doubt:
- **close colours**: nearly one colour on both sides of the cut. The cut may have wandered into the figure or out into the background.
- **cut deep inside the outline**: an area well inside the outline went to the background. That is right for a gap or for a loose outline; it is wrong for a part coloured like the background.

`frame_cuts_figure` names the edges where the picture's frame cuts the figure. The cut-out is cut there too.

Two rounds settle most pictures. Change one thing at a time and look again.

## What to change

| what you see | setting |
|---|---|
| a gap kept: wall between the legs, sky in an arm's loop | a hole in the gap |
| sky or wall left between flying strands | a wider band in a box round them (24 to 32), or a drop point in each gap |
| a pale part eaten where it meets a pale background (light hair over a yellow cushion, a white sock on a white sheet) | a narrower band in a box there (8), and keep points on the part |
| a strip of background kept along an edge (the top of a wall under a hand) | a narrower band in a box there, or a drop point on the strip |
| a thin thing lost (a cord, a staff, a strand outside the outline) | a polygon round it, keep points along it |
| the outline cuts through hair or a hand | redraw the outline outside it |
| a whole part lost, coloured like what is behind it | keep points on it; if that fails, a painted trimap |
| the colours cannot tell at all (black hair on a night sky) | a painted trimap over that stretch |

## When to ask the person

Ask the person for one sentence about what is wrong, never for points or boxes, and turn the sentence into the outline file yourself:
- "the plush is part of her": draw a polygon round it;
- "keep the hair lying on the bed": move the outline out round those strands, then add keep points;
- "her hand is cut off": redraw the outline there.

Where the colours cannot settle a stretch, ask the person to paint a trimap:
- a layer over the picture, the same size;
- white where the figure surely is, black where the background surely is, mid grey where they are unsure;
- exported as a PNG.

Pass it with `--trimap`. It overrides everything else wherever it is not grey, so a few strokes over the trouble spot are enough.

## Putting the figure back

```bash
python scripts/cutout.py scene.png outline.json cut
python scripts/prep.py cut/figure.png cut/fig.png --scale 2     # prints the crop "box" and "upscaled"
python scripts/auto_parts.py cut/fig.png cut/subject.json --upscaled 2 --hints hints.json
python scripts/refinish.py cut/subject.json styles/tv-cel.json cut/fig_cel.png
```

The background can stay as it is, or get a finish of its own:
- `scene_subject.py` on `cut/background.png`;
- `refinish.py` with a scene style.

Then `composite.py` puts the figure back with a scene file:
- the frame is the picture's size;
- the background is the original picture, `background.png` or its finish;
- the figure's `place` is `[box x0, box y1, 1 / upscaled]`, from prep's output.

`--raw` gives the plain paste-up, back exactly where it was; without it, the camera layers apply (compositing.md).

```json
{"frame": [1024, 1536],
 "background": {"image": "cut/background.png"},
 "layers": [{"image": "cut/fig_cel.png", "place": [264, 1507, 0.5]}]}
```

## Limits

- **No partial transparency.** A veil, glasses, smoke or motion blur comes out wholly figure or wholly background, never see-through.
- **Strands.** Hair finer than the line art loses its tips. The edge's colour is taken from just inside the figure, so the cut-out has no fringe, but sky left between strands stays sky until a wider band or a drop point takes it out.
- **The filled background is not a painting.** Where the figure was, `background.png` holds the colours round it, smoothed. It is meant to be covered by the figure again, not shown alone.
