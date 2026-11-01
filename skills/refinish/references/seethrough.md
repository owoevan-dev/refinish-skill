# Reading the head with models (optional)

`auto_parts.py` finds the face, the hair and the eyes from the picture's colours and lines. Two segmentation models can read them instead:
- **See-Through's part segmentation**: the hair, the face, the eyes, the mouth, glasses, headwear and earrings;
- **SAM 2**: each eye split into its iris, its white and its lashes.

The models only label pixels. They draw nothing: the finish is still the skill's code, painted over the source's own drawing. The skill runs without them as before. Use them when the head is where the parts go wrong:
- recolouring, where an iris must take its new colour whole and the lashes and whites must not;
- a pale iris (grey, silver, pale blue) that the colours read as the white of the eye;
- glasses, a hat, hair falling across the face;
- an iris the colours give to the hair.

The body's garments still come from the colours and the hints. See-Through's body labels are too coarse to name a garment: its `topwear` holds a shirt, a jacket and a tie alike.

## Install (once)

Neither model ships with this skill. Install them from their official repositories into a Python environment of their own, so their large dependencies stay out of the one the skill runs in. Tell the user what will be installed and where first: about 6 GB in all (PyTorch about 3 GB, the two models' weights 2.2 GB). An NVIDIA GPU is strongly recommended.

```bash
python -m venv seethrough-env                      # Python 3.10 to 3.12
# activate it: source seethrough-env/bin/activate   (Windows: seethrough-env\Scripts\activate)
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -m pip install accelerate einops timm matplotlib opencv-python requests wheel setuptools
git clone https://github.com/shitagaki-lab/see-through
git clone https://github.com/facebookresearch/sam2
SAM2_BUILD_CUDA=0 python -m pip install --no-build-isolation -e sam2
```

- **PyTorch**: `cu128` is the build for CUDA 12.8 drivers. For other drivers, or without an NVIDIA GPU, take the install command from pytorch.org. On a CPU the parse runs, far more slowly; it was not measured there.
- **SAM 2**: `SAM2_BUILD_CUDA=0` skips an optional CUDA extension that often fails to build; SAM 2 works without it. In PowerShell, run `$env:SAM2_BUILD_CUDA="0"` first, then the same `pip` line. `--no-build-isolation` builds it against the PyTorch already installed. A build that stops with `invalid command 'bdist_wheel'` needs the `wheel` and `setuptools` from the line before.
- **SAM 2's checkpoint**: download `sam2.1_hiera_large.pt` (0.9 GB) into `sam2/checkpoints/`, by `sam2/checkpoints/download_ckpts.sh` or from `https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt`.
- **See-Through's weights** (`24yearsold/l2d_sam_iter2` on Hugging Face, 1.3 GB) download themselves on the first run, into the Hugging Face cache (`HF_HOME` moves it). That download sends nothing about the picture; after it, the parse makes no network request.

## Licences and credits

Both models are Apache-2.0, code and weights. Installing them, the user takes their licences; this skill contains none of their code or weights.

- **See-Through**: Lin, Li, Qin, Chan, Jin, Liu, Choy and Liu, *See-through: Single-image Layer Decomposition for Anime Characters*, SIGGRAPH 2026 (arXiv:2602.03749); code at github.com/shitagaki-lab/see-through. Its part segmentation, `24yearsold/l2d_sam_iter2`, is fine-tuned from HQ-SAM; its repository there carries a NOTICE file.
- **SAM 2**: Ravi et al., *SAM 2: Segment Anything in Images and Videos*, Meta, 2024 (arXiv:2408.00714); code and checkpoints at github.com/facebookresearch/sam2.

## Running it

Run `scripts/seethrough_parse.py` with the Python of that environment (`seethrough-env/bin/python`; on Windows `seethrough-env\Scripts\python.exe`), on the picture `auto_parts.py` will read (after `prep.py`, if the picture was enlarged):

```bash
seethrough-env/bin/python scripts/seethrough_parse.py IMAGE.png parse.png --seethrough see-through --sam2 sam2
python scripts/auto_parts.py IMAGE.png subject.json --parse parse.png --hints hints.json
```

`SEETHROUGH_DIR`, `SAM2_DIR` and `SAM2_CHECKPOINT` stand in for the two options. `--no-eyes` reads the parts only and leaves the eyes to the colours. The picture is read whole, then again with the head cut out and enlarged: the model reads 1024 pixels a side, and a head is a small part of a figure. It took 8 to 17 seconds a picture on a desktop NVIDIA GPU, the models' loading included.

It writes:
- **`parse.png`**, one label per pixel:

  | label | part |
  |---|---|
  | 0 | outside the figure, or no part sure |
  | 1 to 19 | See-Through's parts, in this order: hair, headwear, face, eyes, eyewear, ears, earwear, nose, mouth, neck, neckwear, topwear, handwear, bottomwear, legwear, footwear, tail, wings, objects |
  | 20 | an iris |
  | 21 | the white of an eye |
  | 22 | lashes, and the lines round the eye |
  | 23 | an eye kept as drawn |

- **`parse.eyes.jpg`**, the review sheet: one row per eye, the doubtful ones first. On the left, the eye enlarged with a grid of the picture's coordinates; on the right, its split: **red** the iris, **blue** the white, **green** the lashes, and the eye's number and status in the corner.
- **JSON**: each part's share of the figure, the head's box, and each eye: its number (left to right), centre, box, status, doubts and pixel counts. `eyes_below_nose` counts the pieces the model called an eye below the nose: they are given to the mouth (a laughing mouth, its teeth white and its tongue round, can read as an eye), or, below the chin, to no part.

Exit code 0: done. 1: done, with doubtful eyes. 2: a bad input, or a model not found (the message says which and where it looked).

What `auto_parts.py --parse` takes from it:
- **The hair and the skin** of the head (the face, the ears and the nose), held: a hint part's growth stops at them, and it takes one of their regions only where one of its points lies (inside its boxes), or with its `within` box. A hint part named `hair` or `skin` adds what its points reach elsewhere.
- **Each split eye**: its iris becomes the part `irises` (kind `eyes`), taken whole by a colour card, with no colour test to thin it; its white `eye-whites` and its lashes `lashes`, both kept as drawn. An eye kept as drawn becomes `eyes-kept`.
- **The brows** (what lies above an eye) go with the hair.
- **Glasses, headwear and earrings** become `eyewear` (kind `metal`), `headwear` and `earwear` (kind `metal`). A hint part of the same name adds to them, its kind replacing theirs.
- **The mouth**, when the parse has one; otherwise the face finder's.
- **The eyes' boxes** for the protected face come from the parse; the hints' eye boxes are used only when the parse holds no face.

A parse of another picture, or of the picture at another size, is refused.

## Checking the eyes

An eye's status is one of four:
- `auto`: split without help, and its proportions look right;
- `doubtful`: its proportions look wrong. Its split is left out of `parse.png`, so `auto_parts.py` reads that eye by colour, as without a parse;
- `fixed`: split from clicks (below);
- `kept`: kept as drawn, by a click file.

Four signs make an eye doubtful:
- no iris found;
- an iris under 15 % of the eye: the segmenter took a catchlight or a pupil;
- lashes over twice the iris: the iris's shaded upper half read as lashes;
- a white under 3 % of the eye: the white taken into the iris.

They are signs, not proofs. An eye drawn half closed has little white and is flagged though its split is right; a split can be wrong and pass. So look at every row of the sheet, the `auto` ones too: the red should cover the whole iris, its shaded top and its pupil included, and stop at its edge; the blue only the white; the green the lash line and the lines round the eye.

## Fixing an eye with clicks

Write an eyes file (`refinish-eyes/1`) for the eyes that are wrong, and run `seethrough_parse.py` again with `--eyes eyes.json`:

```json
{
 "format": "refinish-eyes/1",
 "eyes": [
  {"eye": 0, "iris": [[348, 356], [350, 343]], "white": [[322, 364]]},
  {"eye": 1, "keep": true}
 ]
}
```

- `eye`: its number on the sheet and in the JSON.
- `iris`: one or two points on the iris, in the picture's pixels (read them off the sheet's grid). Put them in the iris's own colour, away from the catchlights and the lash line; for an iris shaded at the top, one in the shade and one in the light.
- `white`: a point well inside each piece of the white. A white point is also a point off the iris, so one on the iris's edge cuts a piece out of the iris: keep it a few pixels clear of the edge.
- `not`: points that are neither (a lock of hair across the eye).
- `keep: true`: the eye stays as drawn under every finish. Use it for an eye no click splits.

Look at the new sheet. Two rounds settle most eyes; an eye still wrong after two rounds is kept as drawn, and the user told so.

Measured on 16 eyes of 8 new pictures, the code frozen before they were opened: 10 were split right without help, and the doubts flagged 5 of the 6 that were wrong; 14 were right after one round of clicks, all 16 after two. Recoloured, every one of the 8 characters had both irises in the card's colour, eyes behind glasses and under bangs included; the same pictures without the parse lost two characters' eyes.

## Limits

- **Small eyes.** An eye a few dozen pixels across gives the segmenter too little to read: enlarge the picture with `prep.py` first, or keep the eye as drawn.
- **Unusual eye designs.** Eyes drawn as heavy angular shapes, with no round iris, are often split wrong; keep them as drawn.
- **Closed eyes** have no iris: they are reported as doubtful (no iris), and `auto_parts.py`'s closed-eye test keeps them as drawn, as without a parse.
- **Hair the parse holds.** The parse can read as hair a thing held near the head (a brush's handle), and the hints' growth stops at the hair it holds. Look for such pieces on the parts sheet: a hint point on each takes it (its part's boxes must hold it), and a part's `within` box takes many at once. After the look, a touch does the same (the Recolor skill's step 6).
- **What the models were trained on.** See-Through learned its parts from anime characters. A semi-realistic painting or a chibi may be read worse; look at the parts sheet as for any draft.
- **Size and speed.** The environment is about 6 GB, and a picture takes seconds on a GPU. For a batch, parse every picture once and keep the `parse.png` files: they do not change with the hints or the style.
