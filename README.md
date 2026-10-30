<p align="center">
  <strong>English</strong> · <a href="README.zh-TW.md">繁體中文</a>
</p>

# refinish-skill

**Don't regenerate it. Re-finish it.**

An [Agent Skill](https://agentskills.io) that changes the art style of a character picture or a background by code, never by generating it again. The drawing, the pose and the design stay exactly as they are; only the finish changes, the way an anime finishing department, a print studio or a pixel artist would change it.

Regenerating a picture in a new style gives you another character: another face, another hand, a costume that drifts. Re-finishing keeps the character, so a whole cast of sprites can share one finish, and a finish can be changed late without redrawing anything.

## What it does

- **37 bundled styles** in eight families, each with pre-production advice and its known limits:

  | Family | Styles |
  |---|---|
  | Anime cel | TV cel, heavy cel, bold ink, film everyday, film night, pastel film, 90s cel, night, sunset |
  | De-AI | light, strong: the picture's own colours and lines, the rendering noise and airbrushed gradients taken out |
  | Duotone and limited inks | the picture's own two colours, navy duotone, two-colour print, sepia, cyanotype, risograph |
  | Painterly | watercolour, gouache, thick paint |
  | Print and line | manga screentone, an animator's key drawing, screen print |
  | Special | ink wash, ukiyo-e woodblock, Ben-Day pop art, neon sign, stained glass, paper cut, charcoal, soft pastel, die-cut sticker |
  | Pixel | 96 px character sprite, 192 px portrait sprite |
  | Scenes | woodblock, ink wash and watercolour landscapes |

- **Parts, not pixels.** A subject file says what each part of the picture is (skin, hair, each garment), so each material is painted from its own colour model. It is drafted automatically and corrected with a few hint points. A same-material guard gives stray pixels back to their material before painting, and every result is checked against its source.
- **Match a reference.** `fit_style.py` measures the finish of reference pictures (line darkness, chroma, flatness, edge softness, grain) and fits a style to them round by round. The references are measured, never copied.
- **Tweak by words.** `tweak_style.py` turns "softer shadows", "more vivid", "陰影柔一點" or "線を太く" into parameter steps, and names the measured number each one should move.
- **Relight.** A night or sunset colour model made from the day one in linear light, or a theatrical film's night grade fitted to measurements of night stills.
- **Composite.** `composite.py` lays figures over a background with depth of field and bokeh in linear light, light wrap, a region-by-region grade, bloom and grain.
- **Mix finishes.** `recipe.py` lays finishes over one picture part by part, with blend modes and opacity: the clothes in watercolour and the face in TV cel, a screentone multiplied over a wash, 30 % of a film's look over a heavy cel.
- **Repair the source.** `repair.py` fixes a source's defects without restyling it: a cut-out's fringe, stray specks, gaps in the line art, colour run across a material's edge.
- **Cut a figure out of its scene.** `cutout.py` takes a character out of a picture with a background from a rough outline. The colours decide the exact edge (GrabCut), holes take out the gaps, and the background is filled behind the figure. Each can then be finished on its own, and the figure put back where it was.

## Measured, not guessed

Two batches of new pictures the code had never seen, the code frozen before each was opened:
- Automatic parts with an agent's hints: 19 of 21, then 20 of 20 labelled right within two rounds (39 of 41).
- The de-AI finish on the same pictures: light 21 of 21, then 17 of 20 (38 of 41); strong 19 of 21, then 16 of 20 (35 of 41). The misses: faces behind glasses the draft could not find, and soft neck shadows cut into steps.
- The woodblock, watercolour and ink engines were compared with public-domain museum scans: paper, darkest ink, flat share and edge darkening.

## Requirements

Python 3.10+ with `numpy`, `opencv-python` and `scipy` (`Pillow` optional). No image model, no network, no GPU.

## Install

**Claude Code**

```
/plugin marketplace add owoevan-dev/refinish-skill
/plugin install refinish-skill@refinish-skill
```

**Other agents**

Copy or link `skills/refinish` into the agent's skills directory, or use [skills.sh](https://skills.sh):

```
npx skills add owoevan-dev/refinish-skill
```

## Quick start

```bash
python skills/refinish/scripts/prep.py source.png image.png --scale 2
python skills/refinish/scripts/auto_parts.py image.png subject.json --upscaled 2
python skills/refinish/scripts/refinish.py subject.json skills/refinish/styles/tv-cel.json out.png
```

Then look at `out.png` beside the source, and at the check's review picture. The skill's own workflow, with hints for better parts, is in [skills/refinish/SKILL.md](skills/refinish/SKILL.md).

## What it does not do

- It does not change the design. Proportions, faces, poses and folds come from the source.
- It does not hide where a picture came from. A generated picture is still generated after any style here, the de-AI styles included. They are a finishing pass, not tuned against any detector.
- It ships no reference pictures, textures or strokes taken from any work. Papers and grains are made by code, and style files hold numbers only.

## License

MIT
