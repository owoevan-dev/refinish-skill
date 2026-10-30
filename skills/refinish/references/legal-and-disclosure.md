# Style, copyright and disclosure

General information to pass on to the user, not legal advice; for a commercial project with a lot at stake, a lawyer in
the user's country. Checked in October 2026; platform rules change, so check the platform's own page before
publishing.

## A style is not protected; expression is

- **United States:** 17 U.S.C. §102(b): copyright never extends to an idea, procedure, process, system, method of
  operation, concept or principle.
- **Japan:** the Agency for Cultural Affairs' 2024 paper *General Understanding on AI and Copyright in Japan*
  (AIと著作権に関する考え方について) treats a style of painting (作風・画風) as an idea, outside protection. An output
  infringes when it shares another work's creative expression (similarity, 類似性) and relied on it (reliance, 依拠性):
  the usual test. The paper has no legal force of its own.
- **Taiwan:** the Copyright Act (著作權法), §10-1, protects a work's expression only, not the ideas, concepts or
  principles in it. In a 2024 ruling on a provisional measure, the Intellectual Property and Commercial Court compared
  two one-stroke drawings by their concrete features (the strokes' direction; the lines' undulation, weight and
  crossings; the layout) and doubted that sharing a concept ("one-stroke drawing") or a school's mood made them
  substantially similar.

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
| Steam | the content survey asks about AI used to make content that ships with the game for players (art, sound, narrative, localization): **pre-generated** content made with AI tools during development, and **live-generated** content made while the game runs, with the guardrails that keep it lawful. AI tools used only for efficiency are not what it asks about. The review compares the build and the store page with the answers. |
| pixiv | a work in which all or most of the production process is carried out by AI is set as AI-generated (「AI生成作品」) when posted, whatever software was used. The guidelines' example includes a generated picture posted after light processing or changes, which covers a generated picture re-finished here. A setting that does not match the work breaks the guidelines, and pixiv may change it. pixiv Requests takes no AI-generated work (since 29 May 2023), and the pixivFANBOX terms prohibit content pixiv defines as AI-generated. |
| others | itch.io, Booth, X and the major stores have their own tags and rules. Look them up for each release. |

## Metadata

The PNGs this skill writes carry no metadata of their own. Content Credentials (C2PA) in a source are not carried
over, since a re-finished picture is a new file.

`scripts/png_note.py OUT.png "..."` writes a plain text note into a PNG (a tEXt chunk, readable by any PNG tool), for
example `"AI-assisted: source generated with an image model; refinished with style tv-cel"`. A project that needs
signed Content Credentials signs its final assets with a C2PA tool of its own.

## Sources

- U.S. Copyright Act, [17 U.S.C. §102(b)](https://www.copyright.gov/title17/92chap1.html#102).
- Agency for Cultural Affairs, Japan: 「[AIと著作権に関する考え方について](https://www.bunka.go.jp/seisaku/bunkashingikai/chosakuken/pdf/94037901_01.pdf)」 (15 March 2024), and its English overview, [*General Understanding on AI and Copyright in Japan*](https://www.bunka.go.jp/english/policy/copyright/pdf/94055801_01.pdf).
- Taiwan: [Copyright Act §10-1](https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=J0070017&flno=10-1) (Laws & Regulations Database, 全國法規資料庫); Intellectual Property and Commercial Court, [ruling 113 Min-Zan-Zi No. 14](https://judgment.judicial.gov.tw/FJUD/data.aspx?ty=JD&id=IPCV,113,%E6%B0%91%E6%9A%AB,14,20241231,1) (智慧財產及商業法院 113 年度民暫字第 14 號民事裁定, 31 December 2024, the one-stroke drawing case).
- Steamworks documentation: [Content Survey](https://partner.steamgames.com/doc/gettingstarted/contentsurvey).
- pixiv: [Guidelines](https://www.pixiv.net/terms/?page=guideline); Help Center, [What is AI-generated work?](https://www.pixiv.help/hc/en-us/articles/13276278766489) and [the AI-generated work settings in the request terms](https://www.pixiv.help/hc/en-us/articles/18935333107737); [pixivFANBOX Terms of Use](https://policies.pixiv.net/en.html#fanbox).
