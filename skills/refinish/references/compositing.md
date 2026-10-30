# Compositing and the camera (撮影処理)

In an anime production the paint is not the last step. The photography department (撮影) lays the cels over the
background and gives the frame its lens: what is in and out of focus, the glow of lights, the light of the background
wrapping the figure's edge, the frame's grade. A re-finished figure pasted flat onto a background looks pasted; the
same figure through these steps sits in the scene.

`scripts/composite.py SCENE.json OUT.png` does those steps. `--raw` gives the plain paste-up, to show the difference.

## The scene file

```json
{"frame": [1920, 1080],
 "background": {"image": "bg.png", "zoom": 1.25, "centre": [0.5, 0.55], "blur": 7.0,
                "grade": {"chroma": 0.8, "regions": [{"hue": [200, 290], "chroma_min": 8, "L": 8.0},
                                                     {"rest": true, "L": 18.0}]}},
 "layers": [{"image": "figure.png", "place": [1050, 1980, 0.62], "wrap": 0.2, "sharpen": 0.4},
            {"image": "shoulder.png", "place": [-80, 1180, 1.4], "blur": 34.0}],
 "camera": {"bokeh": {"shape": "disk", "hot": 3.0, "knee": 0.7},
            "bloom": {"threshold": 0.7, "radius": 14, "amount": 0.25}, "vignette": 0.12, "grain": 0.005}}
```

All sizes are pixels of the frame. Paths are relative to the scene file.

| key | meaning |
|---|---|
| `background.zoom`, `centre` | crop into the background: a longer lens, so what lies behind is larger and closer. It is blurred anyway, so the enlargement shows nothing a lens would not soften. |
| `background.blur` | the background's distance from the focus, as the radius of its blur. |
| `background.grade` | `lift`, `gain`, `chroma`, `cast_a`, `cast_b`, and `regions`: parts of the background told apart by hue (a sky's blue from the ground) and each brought to its own median lightness `L`. A day background turned to night needs this: its sky and its slope sit at nearly the same lightness, and one curve cannot move them apart. |
| `layers[].place` | [left edge, bottom, scale] of the cut-out on the frame. Layers are back to front. |
| `layers[].blur` | that layer's own distance from the focus: 0 sharp, a near shoulder far out of focus 30 or more. Blurred with its alpha, so its silhouette softens too. |
| `layers[].wrap` | light wrap: the light of what lies behind reaching a little way over the layer's edge (`wrap_width` px). 0.15 to 0.25 for a lit background; little or none against a dark one. |
| `layers[].sharpen` | a fine unsharp mask on the lines only, for a cut-out enlarged a little (the flat paint stays smooth). |
| `layers[].grade` | the same grade keys, on the layer alone (a figure warmed toward a fire). |
| `camera.bokeh` | the aperture's shape (`disk`, or `polygon` with `blades` and `rotation`), and how far the brightest lights are pushed above white before the blur (`hot` times, from `knee`), so they open into bright discs instead of grey smears. |
| `camera.bloom` | a soft glow round the frame's brightest lights. |
| `camera.vignette`, `camera.grain` | darker corners; a fine grain over the whole frame (a figure's own grain belongs to its style). |

## How the depth of field is made

Out of focus is not a Gaussian blur: a lens spreads each point into the shape of its aperture, and does it in light,
not in display values. The blur is a disc (or a polygon) convolved in linear light, the brightest values boosted first,
so a lantern out of focus becomes a clean bright disc with an edge, as it does on film. A Gaussian blur in display
values greys the same lantern into a smear.

The figure in focus is laid over the blurred background unblurred. Its edge would then be too clean against the soft
light behind it; the light wrap gives some of that light back over its edge.

## Inside the figure

A depth of field inside one figure (a close-up whose shoulder falls away, a hand reaching to the lens) is a style's
`post` layer, `focus` (references/style-format.md): sharp round the face, softening with distance, with the same
disc and the same lights. It keeps the figure's own outline; in a scene, a whole layer out of focus is better made
with that layer's `blur`.

## Matching the figure to the scene

A cel figure belongs in front of a painted background, as in anime production: the background re-finished with `deai-light` rather than a cel style (presets.md, Scenes), and the layer and background grades used to bring the two into one light.

The camera does not relight. A figure meant for a night scene gets its night first: a style with a `relight` layer
or `scripts/refinish.py --hour night` (a TV night colour model) or `--hour film-night` (a film's night grade). A
figure by a fire can take a layer `grade` with a warm cast as well. Then the camera.
