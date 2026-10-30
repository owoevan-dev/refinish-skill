# Style, copyright and disclosure

General information to pass on to the user, not legal advice; for a commercial project with a lot at stake, a lawyer in
the user's country. Checked in October 2026; platform rules change, so check the platform's own page before
publishing.

## A style is not protected; expression is

- **Taiwan:** 著作權法 §10-1 protects a work's expression only, not the ideas, concepts or principles in it. The courts
  compare concrete features (the strokes' direction, the lines' waves and weights, the layout); a shared concept or
  school of painting is not infringement on its own.
- **United States:** 17 U.S.C. §102(b): copyright never extends to an idea, procedure, process, system, method of
  operation, concept or principle.
- **Japan:** the Agency for Cultural Affairs' 2024 「AIと著作権に関する考え方について」 treats 作風・画風 as ideas, outside
  protection. An output infringes when it shares another work's creative expression (類似性) and relied on it
  (依拠性): the usual test. The paper has no legal force of its own.

What this skill measures and writes into a style file is the finish:
- line darkness;
- chroma;
- the flatness of the shading;
- grain.

All of these are numbers about technique. The drawing the finish is laid on is the user's own.

## Where the real risks lie

1. **Copying expression, not style.** A result that reproduces a specific work's characters, compositions or
   recognisable designs is a copy of expression whatever its finish. This skill re-finishes the user's own picture;
   it does not redraw anyone else's.
2. **Redistributing the references.** The pictures a style was measured from stay where the user keeps them. They are
   never copied into the project, a style file or anything shared; a style file holds numbers only.
3. **Names.** A style is named after its technique (`film-everyday-cel`, `ukiyo-e-woodblock`), never after the work,
   studio or artist it was measured from. A name can claim an association a finish cannot.
4. **Passing off.** A result presented as official art of an existing work, or as the hand of a named artist, misleads
   whatever the law says about style.
5. **Accidental closeness.** A design that comes out close to an existing one can still raise the question of reliance
   (依拠). A reverse image search of a finished key visual is a cheap check before publishing.

## Disclosure

The finish does not change where a picture came from. A source made with an image model is still AI-generated after
any style here, the de-AI styles included. Those styles exist for a cleaner, more deliberate finish. They are not a
way to pass a generated picture off as hand-made, and they are not tuned against AI detectors.

| platform | rule (as of October 2026) |
|---|---|
| Steam | the AI content disclosure on the store page covers **pre-generated** content that ships with the game or appears in its marketing (art, sound, text made with AI tools) and **live-generated** content made while the game runs (with its guardrails described). Tools used behind the scenes for efficiency need no disclosure. |
| pixiv | a work made with generative AI is set as 「AI生成作品」 when posted; leaving it unset is a guideline violation, and AI works are not allowed on pixiv Requests or FANBOX. |
| others | itch.io, Booth, X and the major stores have their own tags and rules. Look them up for each release. |

## Metadata

The PNGs this skill writes carry no metadata of their own. Content Credentials (C2PA) in a source are not carried
over, since a re-finished picture is a new file.

`scripts/png_note.py OUT.png "..."` writes a plain text note into a PNG (a tEXt chunk, readable by any PNG tool), for
example `"AI-assisted: source generated with an image model; refinished with style tv-cel"`. A project that needs
signed Content Credentials signs its final assets with a C2PA tool of its own.

## Sources

- 著作權法 §10-1 (全國法規資料庫); 智慧財產法院 113 年度民暫字第 14 號裁定 (the one-stroke drawing case).
- U.S. Copyright Act, 17 U.S.C. §102(b).
- 文化庁「AIと著作権に関する考え方について」 (2024).
- Steamworks documentation, content survey (AI disclosure).
- pixiv guidelines and help on AI-generated works.
