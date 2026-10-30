# Checks on a finished picture

`scripts/refinish.py` checks every picture it writes, on the finish before its layers. To check one again on its own: `scripts/check_output.py subject.json out.png --style STYLE`, adding `--hour H` if the picture was made with it. With the style named, the part map is guarded as refinish.py guarded it and the checks are that engine's, except what the file cannot show: under post layers (a relight, paper, grain) only the part map is checked, and for an engine built on a cel finish the part map and the look checks. The report's `note` says which; refinish.py's own report remains the full check. A pixel, sticker or neon result is another size than its source and cannot be checked again on its own: read refinish.py's report and look at the result.

- **Report**: JSON with a verdict (`pass`, `warn` or `fail`) and the findings. Each finding has its check, its part, a box and what to do. A `fail` makes the script exit 1.
- **Review picture**: `<out>.check.jpg` shows the result with each finding boxed and numbered (red for FAIL, orange for WARN).
- **What to do**: fix every FAIL before the picture is used, and look at each WARN.

| check | level | what it finds | usual cause | fix |
|---|---|---|---|---|
| P1 | WARN | a thick blob much darker or lighter than the rest of its part | a misfit in the part map (a dark lock labelled skin) | a hint point, or a sample |
| P2 | WARN | the middle of an eye's box labelled hair or cloth | an iris as dark as the hair, read as hair | give the irises a part of kind `eyes` |
| M1 | FAIL (WARN when near-white or near-black) | a patch inside a part with the colour of a part beside it and none of its own | a piece of one part labelled as another (a neck read as the gold collar beside it, a waistband read as the jacket) | move its region, or add a hint point |
| O1 | FAIL | a patch kept as drawn while the rest of its part changed | a protected box keeping hair or cloth, or a region left out of its part | tighten the box, or give the region its part |
| O2 | FAIL | the white of an eye painted as skin | eye whites a few steps from the skin's colour | give the whites a part of kind `eyes` |
| O3 | FAIL | a dark line along an edge where the frame cuts the figure | an outline drawn where the figure goes on past the frame | (the engine's outline skips frame cuts; report it) |
| O4 | WARN | the soft edge jumps in lightness more than in the source | a halo | look at the edge at full size |
| O5 | FAIL | an iris labelled hair or cloth and repainted | the iris read as hair, outside the box's keeping | give the irises a part of kind `eyes` |
| O6 | FAIL | a mass of pure black painted as its part | a keyhole read as gold, a shadow mass read as skin | give the black a part of kind `accessory` |
| O7 | FAIL (WARN for a light skin) | a darker skin printed far lighter, or a light one far darker than the rest of the figure | a style's skin convention applied to every skin | adjusting.md, "Skin painted another colour" |
| O8 | FAIL | the face's tone stepping along a protected box's straight edge | a feature kept or inked by a fixed level against a skin repainted round it | a tighter box, or the box's `de` (adjusting.md) |
| O9 | WARN | a dark part broken into patches far more than in the source | a texture or a wash's drift on a dark area | the engine's texture settings (adjusting.md) |

**Where the checks run:**
- P1 to O6 run on the cel or paint finish. For an engine built on a cel finish (print, woodblock, wash, pencil, pixel, tone, pop, glass, paper cut, drawing, sticker, neon), they run on that cel base.
- O7 to O9 run on every engine's own result, the duotones included.

**How the O7 to O9 thresholds were set:** on 740 results, 37 styles on 20 generated figures, before and after the fixes they point at.
- **Before the fixes**, they found:
  - the woodblock's pale skin on all four darker-skinned figures, in both woodblock styles;
  - the screentone's boxes on the same four;
  - the charcoal's mottle.
- **They are not run** where a style empties or sinks the fills by design: O7 on neon and the pencil, O9 on neon, pixel and manga.
- **They are heuristics:** look at what they point at.

## What a part's own shading is not

- **M1** compares a patch with the part's own colours. It flags only a patch whose colour the part has nowhere else and which a touching part shares. The shaded tones a part has all over (the red-orange shadows of orange hair) are its own and are never flagged. A near-white or near-black patch is only a WARN: those colours are shared by too many materials (a white trim on a jersey beside white shorts, stitching, the ink) for the patch to prove a misread part.
- **O1** never counts the lines, pure black or pure white. Those are left as drawn by design. It also never counts a patch the same colour as the new paint round it: on a painted source the flat paint can land on the source's own colour where nothing was kept, and only a patch that stands out shows.

## How the checks were tested (2026-10-29)

**The known mistakes are caught.** Nine mistakes met while building the styles were made again, and each was caught by the check meant for it:
- the neck painted gold;
- a lock of hair painted as the jacket;
- keyholes painted gold;
- the black jaw painted as skin;
- the waistband painted as the jacket;
- eye whites painted as skin;
- hair kept in the eyes' boxes;
- a mottled iris;
- an outline along a frame cut.

Some were reproduced by undoing their fix and re-finishing. Others were put into a good result directly.

**New pictures show their limits.** On 16 characters the checks had never seen, O7 flagged 1 of 57 skins printed the wrong colour and O8 8 of 15 boxes round the features, with no false alarms (CHANGELOG, Known issues). A pass is not a sign-off: look at every result (SKILL.md, step 5).

**Good work passes.** Four accepted results gave no FAIL:
- a bold-ink TV cel;
- a heavy cel;
- a night film frame;
- a TV cel.

## The de-AI engine's check

| check | level | finds | likely cause | fix |
|---|---|---|---|---|
| H1 | FAIL | a patch of paint whose a*b* moved more than 8 (after the style's chroma factor) | two materials of near colour with no line between them, read as one | look at the patch; if the source really has no line there, use the light setting or name the parts and use a cel style |
