<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-dark-1200.png">
    <img src="assets/brand/logo-1200.png" alt="Refinish" width="440">
  </picture>
</p>

<p align="center">
  <strong>English</strong> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <a href="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml"><img src="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-1f1c1a" alt="Licence: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-1f1c1a" alt="Python 3.10 or newer">
</p>

<p align="center"><strong>Don't regenerate it. Re-finish it.</strong></p>

Refinish is an [Agent Skill](https://agentskills.io) for re-finishing art you already have. It keeps the drawing (the line art, the pose, the face, the costume) and repaints the finish: the shape of the shadows, the ink of the lines, the palette, the medium. It comes with 37 finishes, from TV anime cel and watercolour to woodblock prints, manga screentone and pixel sprites. It can also take the generic AI look off generated art.

Everything happens in Python, with NumPy and OpenCV. No image model is involved, so the character that comes out is the character that went in.

<p align="center">
  <img src="docs/images/hero.jpg" alt="One character shown six times: the source picture, then watercolour, ukiyo-e woodblock, manga screentone, stained glass and a pixel sprite">
</p>

## Why not just regenerate it?

Ask an image model to redraw a character in a new style and you get a slightly different character. The face shifts, the hands are drawn again, the costume drifts. For a single illustration that may be fine. For a cast of sprites that have to match, it isn't.

Re-finishing works the other way round. The drawing stays fixed and only the finish moves. A whole cast can share one look, and the look can still change late in a project without anything being redrawn.

## Less of the AI look

Generated art often has a look people spot at a glance: the same fine detail everywhere, airbrushed gradients, extra gloss and noise. Re-finishing replaces it with one consistent, deliberate technique: the flat tones of cel, the washes of watercolour, the lines of a print. To keep the picture as it is and only clean those traces off, use the de-AI finishes, light or strong.

A finish changes the paint, not the picture. The AI look that comes from the composition, the detail density and the light has to be avoided when the picture is generated ([source-spec.md](skills/refinish/references/source-spec.md)). Nor does a finish hide where a picture came from: a generated picture is still generated after it, and whatever a platform asks you to disclose, you still disclose.

## What changes, and what doesn't

| | |
|---|---|
| **Changes** | Line weight, colour and texture; the shape and number of shadow tones; highlights; palette and light, night and sunset included; the medium (paint, paper, ink, print screens, pixels) |
| **Stays** | Proportions, the way the eyes are drawn, the pose, the folds, the composition |

The second row is deliberate. If you want a character drawn the way another artist draws faces, this is not that tool. If you want your own picture finished the way an anime paint department, a print studio or a pixel artist would finish it, it is.

## Finishes

<p align="center">
  <img src="docs/images/styles.jpg" alt="The sample character in 34 finishes, grouped by family: anime cel, cleaner finishes, two-colour prints, paint, print and line, pixel, and special techniques">
</p>

| Family | Finishes |
|---|---|
| Anime cel | TV cel, heavy cel, bold ink, film everyday, film night, pastel film, 90s cel, TV night, TV sunset |
| Cleaner finish | de-AI light and strong: the picture's own colours and lines, with the rendering noise and the airbrushed gradients taken out |
| Two colours and limited inks | the picture's own two colours, navy duotone, two-colour print, sepia, cyanotype, risograph |
| Paint | watercolour, gouache, thick paint |
| Print and line | manga screentone, an animator's key drawing, screen print |
| Special | ink wash, ukiyo-e woodblock, Ben-Day pop art, neon sign, stained glass, paper cut, charcoal, soft pastel, die-cut sticker |
| Pixel | 96 px character sprite, 192 px portrait sprite |
| Landscape | woodblock, ink wash and watercolour scenes |

[presets.md](skills/refinish/references/presets.md) has a note on each finish: what it needs, how to prepare a picture for it, and where it falls short.

## Backgrounds and scenes

Backgrounds are handled differently. A painted background has few lines and long gradients (sky, haze, a room falling into shadow), and flat cel tones would cut those gradients into blotches. Anime doesn't cel-paint its backgrounds either. The cels are the characters, laid over a painted background.

So a background takes the cleaner de-AI finish or a landscape finish, and the character goes on top in its cel finish. `composite.py` brings the two together with depth of field, light wrap and a grade that puts both in the same light.

A character drawn into a scene can be cut out first with `cutout.py`. You draw a rough outline, the colours decide the exact edge, and you also get the background back with the figure's place filled, ready to be finished on its own.

## Beyond a filter

- **Parts, not pixels.** A subject file says what each part of the picture is: skin, hair, each garment. Every material is painted from its own colours, so a red ribbon never bleeds into the skin beside it. The file is drafted automatically and corrected with a few hint points.
- **Every result is checked.** Each finish is compared with its source for parts, colours, the outline, lost features, skin printed the wrong colour, boxes round the face and mottled dark cloth. Every warning names a place and a likely cause.
- **Match a reference.** `fit_style.py` measures the finish of reference pictures (line darkness, chroma, flatness, edge softness, grain) and fits one of the cel styles to them, round by round. The references are measured, never copied. The design (proportions, how the eyes are drawn) and the scene's light do not carry over; for a reference in another technique, start from the nearest style and change it in words (`tweak_style.py`).
- **Adjust it in words.** `tweak_style.py` turns "softer shadows", "more vivid", "陰影柔一點" or "線を太く" into parameter steps, and tells you which measurement should move.
- **Relight.** Night and sunset are worked out from the day colours in linear light, or come from a cinematic night grade.
- **Mix finishes.** `recipe.py` layers finishes part by part: the clothes in watercolour and the face in cel, or a screentone multiplied over a wash.
- **Repair the source.** `repair.py` fixes a cut-out's fringe, stray specks, gaps in the line art and colour that ran across a material's edge, without restyling anything.

## How well it works

The figures below come from the project's own runs on pictures the code had never seen; those pictures are not in this repository. The code is frozen and the pass marks are written down before the pictures are opened, and a set that has been looked at is used for development only.

- **Parts.** On two sets of new characters, parts drafted with an agent's hints were right for 39 of 41 within two rounds.
- **All 37 finishes on 16 new characters** (10 with darker skin, 4 with soft airbrushed shading). 21 finishes passed every measure:
  - every cel finish except the sunset and 90s ones;
  - both de-AI finishes;
  - the paint finishes;
  - stained glass, paper cut and the sticker.

  No finish left blotches on dark cloth.
- **Where it falls short.** These are open issues, listed in the [changelog](CHANGELOG.md):
  - manga screentone prints darker skin too pale;
  - pop art still leaves boxes round the face;
  - the ukiyo-e print lightens tan skin;
  - soft airbrushed sources break into ragged shadows under every flat-tone finish.
- **Against the real thing.** The woodblock, watercolour and ink finishes were compared with public-domain museum scans for paper colour, darkest ink, flat area and edge darkening.
- **Match a reference** (development tests, not frozen runs). On a closed loop (references drawn in one bundled style, fitted from another on a different character), three rounds brought 6 of the 8 finish numbers within 10%. On frames from a TV anime, 4 to 5 of 8: the softness that compositing adds to the frames is beyond the cel finishes.

## Install

**Claude Code**

```
/plugin marketplace add owoevan-dev/refinish-skill
/plugin install refinish-skill@refinish-skill
```

**Other agents**

Copy or link `skills/refinish` into your agent's skills folder, or use [skills.sh](https://skills.sh):

```
npx skills add owoevan-dev/refinish-skill
```

The scripts need Python 3.10 or newer with `numpy`, `opencv-python` and `scipy` (`Pillow` is optional). No GPU, no network, no model downloads.

## Using it

With the skill installed, ask your agent in plain words:

> Give everything in `sprites/` a TV anime cel finish. Same look on every picture.

> This portrait looks too AI. Clean it up, but keep the colours.

> Cut the girl out of `street.png`, give her a 90s cel finish and put her back.

> Match the finish of the frames in `refs/` on my character: the lines, the colours, the shading. Tell me what does not carry over.

The agent follows [SKILL.md](skills/refinish/SKILL.md). It checks the picture, makes the subject file, runs the finish, and looks at the result before showing it to you. The scripts also work on their own:

```bash
python skills/refinish/scripts/check_input.py source.png
python skills/refinish/scripts/prep.py source.png image.png --scale 2
python skills/refinish/scripts/auto_parts.py image.png subject.json --upscaled 2
python skills/refinish/scripts/refinish.py subject.json tv-cel out.png
```

## Limits

- It doesn't change the design. Proportions, faces, poses and folds come from the source.
- The parts are drafted automatically, and the draft is often wrong somewhere: an eye missed when it is closed or winking, a lock of hair read as the clothes it lies on. A patch in another material's colour (that lock painted like the clothes) almost always comes from such a mistake, and goes once the parts are right. Whenever you see one, say what is wrong in a sentence, such as "this lock is hair". You never need to give boxes or points: the agent turns the sentence into hints and runs again. Clean cel pictures settle within two rounds; semi-realistic paintings, dense patterns and black on black are harder. When the parts will not come right, the agent merges parts, finishes only the parts that are right, or uses a finish that needs no parts ([subject-file.md](skills/refinish/references/subject-file.md)).
- Soft airbrushed shading gives the flat cel finishes less to work with; the paint finishes cope better. Blotches inside one material come from it, not from the parts. [source-spec.md](skills/refinish/references/source-spec.md) explains how to ask an image model for a picture that finishes well.
- Cut-outs have hard edges. A veil, a lens or smoke comes out as wholly figure or wholly background.
- It doesn't hide where a picture came from. A generated picture is still generated after any finish here, the de-AI ones included, and none of them is tuned against any detector.

## Documentation

| | |
|---|---|
| [SKILL.md](skills/refinish/SKILL.md) | The workflow the agent follows, and every script |
| [presets.md](skills/refinish/references/presets.md) | All 37 finishes: what each needs, how to prepare for it, its limits |
| [subject-file.md](skills/refinish/references/subject-file.md) | Parts, hints, and the failure modes measured on them |
| [adjusting.md](skills/refinish/references/adjusting.md) | What to change when something looks wrong |
| [cutout.md](skills/refinish/references/cutout.md) | Cutting a figure out of a scene and putting it back |
| [compositing.md](skills/refinish/references/compositing.md) | Backgrounds, depth of field and light wrap |
| [style-format.md](skills/refinish/references/style-format.md) | Writing or changing a style file |
| [legal-and-disclosure.md](skills/refinish/references/legal-and-disclosure.md) | Style and copyright, and what Steam and pixiv ask for |

## Contributing

Bug reports and requests for new finishes are welcome as [issues](https://github.com/owoevan-dev/refinish-skill/issues). Pull requests from outside the project are closed for now; [CONTRIBUTING.md](CONTRIBUTING.md) explains why, and what to do instead.

## Licence

[MIT](LICENSE). The sample character in the pictures above was made with an image model for this README; every finish shown is this skill's output. The test pictures in the skill's `evals` folder are drawn by code, and the logo's lettering is Noto Serif TC (SIL Open Font License) turned into outlines.
