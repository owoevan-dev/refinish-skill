<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-dark-1200.png">
    <img src="assets/brand/logo-1200.png" alt="Refinish" width="440">
  </picture>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <strong>繁體中文</strong> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <a href="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml"><img src="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml/badge.svg" alt="測試"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-1f1c1a" alt="授權：MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-1f1c1a" alt="Python 3.10 以上">
</p>

<p align="center"><strong>不重新生成，只重新完稿。</strong></p>

Refinish 是一個 [Agent Skill](https://agentskills.io)，替手邊已有的圖重新完稿。畫的本身（線稿、姿勢、臉、服裝）保持不動，重畫的是完稿：陰影的形狀、線條的墨色、配色和媒材。內建 37 種完稿方式，從電視動畫賽璐璐、水彩，到浮世繪木版、漫畫網點和像素圖。也能讓 AI 生成的素材擺脫常見的 AI 味。

全部用 Python（NumPy 與 OpenCV）處理，不經過任何影像生成模型，所以出來的角色，就是放進去的那個角色。

<p align="center">
  <img src="docs/images/hero.jpg" alt="同一個角色的六個版本：原圖、水彩、浮世繪木版、漫畫網點、彩繪玻璃、像素圖">
</p>

## 為什麼不直接重新生成？

請影像模型用新畫風重畫一個角色，得到的會是有點不一樣的角色：臉變了一點，手重畫過，服裝細節也跟著跑掉。單張插圖也許無所謂，但一整組必須對得上的立繪就不行。

重新完稿反過來做：畫固定不動，只換完稿。整組角色可以共用同一種風格，到了專案後期要換風格，也不必重畫任何一張。

## 降低 AI 感

生成的圖常帶著一眼就認得出的 AI 味：處處一樣精細、噴槍般的漸層、多餘的光澤和雜訊。重新完稿用一種一致、刻意的手工技法取代這些痕跡：賽璐璐的平塗、水彩的暈染、版畫的線條。只想保留原本的樣子、清掉這些痕跡的話，就用去 AI 味（輕、重）完稿。

完稿改的是上色，不是畫面本身。構圖、細節密度和光線帶來的 AI 感，要在生成時就避免（見 [source-spec.md](skills/refinish/references/source-spec.md)）。它也不會隱藏圖片的來源：生成的圖經過完稿仍然是生成的，平台要求揭露的，照樣要揭露。

## 改什麼、不改什麼

| | |
|---|---|
| **會改** | 線條的粗細、顏色與質感；陰影的形狀與階數；高光；配色與光線，包括夜晚與夕陽；媒材（顏料、紙、墨、網點、像素） |
| **不改** | 比例、眼睛的畫法、姿勢、衣褶、構圖 |

第二列是刻意的。如果你想要的是「照另一位畫師的方式畫臉」，這不是那種工具；如果你想讓自己的圖，用動畫上色部門、版畫工房或像素畫師的方式完稿，那就是。

## 完稿方式

<p align="center">
  <img src="docs/images/styles.jpg" alt="範例角色的 34 種完稿，依類別排列：動畫賽璐璐、乾淨的完稿、雙色印刷、繪畫、版畫與線稿、像素、特殊技法">
</p>

| 類別 | 完稿方式 |
|---|---|
| 動畫賽璐璐 | 電視動畫、濃厚、粗墨線、電影日常、電影夜景、粉彩電影、90 年代、電視夜景、電視夕陽 |
| 乾淨的完稿 | 去 AI 味（輕、重）：保留原圖的顏色與線條，去掉渲染雜訊與噴槍漸層 |
| 雙色與少色印刷 | 原圖自己的兩色、深藍雙色、雙色印刷、棕褐、藍曬、Riso 孔版 |
| 繪畫 | 水彩、不透明水彩、厚塗 |
| 版畫與線稿 | 漫畫網點、動畫原畫、絹印 |
| 特殊技法 | 水墨、浮世繪木版、普普藝術網點、霓虹燈、彩繪玻璃、剪紙、炭筆、粉彩、貼紙 |
| 像素 | 96 px 角色、192 px 頭像 |
| 風景 | 木版、水墨、水彩風景 |

每種完稿在 [presets.md](skills/refinish/references/presets.md) 都有說明：需要什麼、原圖怎麼準備最好、做不到的地方。

## 背景與場景

背景的處理方式不同。手繪背景線條少，大多是長漸層（天空、霧氣、慢慢暗下去的室內），平塗的賽璐璐色階會把這些漸層切成一塊一塊。動畫本來也不用賽璐璐塗背景：賽璐璐是角色，疊在手繪的背景上。

所以背景用乾淨的去 AI 味完稿或風景完稿，角色用賽璐璐完稿疊在上面。`composite.py` 負責把兩者合起來，加上景深、光線包覆，以及讓兩者落在同一種光線裡的調色。

畫在場景裡的角色，可以先用 `cutout.py` 摳出來：畫一圈大概的外框，精確的邊緣交給顏色判斷，同時拿回補好角色位置的背景，可以另外完稿。

## 不只是濾鏡

- **以部位為單位，不是以像素。** 主體檔（subject file）標出圖裡每個部位是什麼：皮膚、頭髮、每件衣服。每種材質用它自己的顏色上色，紅色緞帶不會滲進旁邊的皮膚。主體檔會自動起草，再用幾個提示點修正。
- **每張結果都會檢查。** 每次完稿都和原圖比對：部位、顏色、外框、消失的五官細節、被印成別的顏色的皮膚、臉部周圍的方框、深色布料上的斑塊。每個警告都會指出位置和可能的原因。
- **對照參考圖。** `fit_style.py` 量測參考圖的完稿（線條深淺、彩度、平塗程度、邊緣柔和度、顆粒），一輪一輪調出相符的風格。參考圖只量測，不複製。
- **用文字調整。** `tweak_style.py` 把「陰影柔一點」「再鮮豔一點」「線を太く」這類說法轉成參數步驟，並告訴你哪個量測值應該跟著變。
- **改變時段。** 夜晚與夕陽由白天的顏色在線性光中推算，或套用電影感的夜景調色。
- **混合完稿。** `recipe.py` 依部位疊加完稿：衣服用水彩、臉用賽璐璐，或在水彩上以色彩增值疊一層網點。
- **修復原圖。** `repair.py` 修正去背留下的邊、雜點、線稿斷口、跨過材質邊界的滲色，而且不改畫風。

## 實際表現

每項修改都用程式沒看過的圖驗證：開圖前先凍結程式、寫好合格標準；看過的圖之後只用於開發。

- **部位。** 在兩組新角色上，搭配 agent 的提示點，41 張中有 39 張在兩輪內每個部位都正確。
- **37 種完稿套用在 16 個新角色上**（10 個膚色較深，4 個是柔和的噴槍上色），21 種完稿通過所有量測：
  - 除了夕陽與 90 年代以外的所有賽璐璐完稿；
  - 兩種去 AI 味完稿；
  - 繪畫類完稿；
  - 彩繪玻璃、剪紙與貼紙。

  所有完稿都沒有在深色布料上留下斑塊。
- **還沒做好的地方。** 以下都列在[更新紀錄](CHANGELOG.md)中，尚待修正：
  - 漫畫網點會把較深的膚色印得太淺；
  - 普普藝術仍會在臉周圍留下方框；
  - 浮世繪木版會把小麥色皮膚印淡；
  - 柔和噴槍上色的原圖，在所有平塗類完稿下陰影邊緣都會破碎。
- **與真品比對。** 木版、水彩、水墨完稿與博物館的公有領域掃描圖比對過紙色、最深墨色、平塗面積與邊緣加深。

## 安裝

**Claude Code**

```
/plugin marketplace add owoevan-dev/refinish-skill
/plugin install refinish-skill@refinish-skill
```

**其他 agent**

把 `skills/refinish` 複製或連結到 agent 的 skills 資料夾，或使用 [skills.sh](https://skills.sh)：

```
npx skills add owoevan-dev/refinish-skill
```

腳本需要 Python 3.10 以上，以及 `numpy`、`opencv-python`、`scipy`（`Pillow` 可選）。不需要 GPU、網路，也不用下載模型。

## 使用方式

裝好 skill 後，直接用平常的話請 agent 處理：

> 把 `sprites/` 裡的圖都改成電視動畫賽璐璐，每張風格要一致。

> 這張立繪 AI 味太重，幫我清乾淨，但顏色保持原樣。

> 把 `street.png` 裡的女孩摳出來，改成 90 年代賽璐璐，再放回原位。

agent 會照 [SKILL.md](skills/refinish/SKILL.md) 的流程：先檢查原圖、建立主體檔、套用完稿，自己看過結果才交給你。腳本也可以單獨使用：

```bash
python skills/refinish/scripts/check_input.py source.png
python skills/refinish/scripts/prep.py source.png image.png --scale 2
python skills/refinish/scripts/auto_parts.py image.png subject.json --upscaled 2
python skills/refinish/scripts/refinish.py subject.json tv-cel out.png
```

## 限制

- 不改設計。比例、臉、姿勢與衣褶都來自原圖。
- 柔和的噴槍上色讓平塗類的賽璐璐完稿較難處理，繪畫類完稿比較能應付。[source-spec.md](skills/refinish/references/source-spec.md) 說明怎麼請影像模型畫出容易完稿的圖。
- 去背是硬邊。面紗、鏡片、煙霧，不是整塊算角色，就是整塊算背景。
- 不會隱藏圖片的來源。AI 生成的圖經過任何完稿（包括去 AI 味）都仍然是 AI 生成的，這些完稿也沒有針對任何偵測工具調整。

## 文件

| | |
|---|---|
| [SKILL.md](skills/refinish/SKILL.md) | agent 依循的流程，以及每支腳本 |
| [presets.md](skills/refinish/references/presets.md) | 全部 37 種完稿：各自需要什麼、怎麼準備、有哪些限制 |
| [subject-file.md](skills/refinish/references/subject-file.md) | 部位、提示點，以及實測到的失敗情況 |
| [adjusting.md](skills/refinish/references/adjusting.md) | 看起來不對時該改什麼 |
| [cutout.md](skills/refinish/references/cutout.md) | 從場景摳出角色，再放回原位 |
| [compositing.md](skills/refinish/references/compositing.md) | 背景、景深與光線包覆 |
| [style-format.md](skills/refinish/references/style-format.md) | 撰寫或修改風格檔 |
| [legal-and-disclosure.md](skills/refinish/references/legal-and-disclosure.md) | 畫風與著作權，以及 Steam 和 pixiv 的要求 |

文件本身以英文撰寫。

## 參與貢獻

歡迎用 [Issues](https://github.com/owoevan-dev/refinish-skill/issues) 回報問題或許願新的完稿方式。目前不接受外部的 pull request，原因與替代做法寫在 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權

[MIT](LICENSE)。上方圖片中的範例角色與街景，是為這份 README 用影像模型生成的；圖中所有完稿都是這個 skill 的輸出。
