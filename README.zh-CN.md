<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-dark-1200.png">
    <img src="assets/brand/logo-1200.png" alt="Refinish" width="440">
  </picture>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <strong>简体中文</strong> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <a href="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml"><img src="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml/badge.svg" alt="测试"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-1f1c1a" alt="许可证：MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-1f1c1a" alt="Python 3.10 及以上">
</p>

<p align="center"><strong>不重新生成，只重新完稿。</strong></p>

Refinish 是一个 [Agent Skill](https://agentskills.io)，用来给手头已有的图重新完稿。画面本身（线稿、姿势、脸、服装）保持不变，重新处理的是完稿：阴影的形状、线条的墨色、配色和画材。内置 37 种完稿方式，从电视动画赛璐璐、水彩，到浮世绘木版、漫画网点和像素画。也能让 AI 生成的素材摆脱常见的 AI 味。

全部处理都用 Python（NumPy 和 OpenCV）完成，不经过任何图像生成模型，所以出来的角色，就是放进去的那个角色。

<p align="center">
  <img src="docs/images/hero.jpg" alt="同一个角色的六个版本：原图、水彩、浮世绘木版、漫画网点、彩绘玻璃、像素画">
</p>

## 为什么不直接重新生成？

让图像模型用新画风重画一个角色，得到的会是一个有点不一样的角色：脸变了一点，手重画过，服装细节也跟着走样。单张插画或许无所谓，但一整套必须对得上的立绘就不行了。

重新完稿反过来做：画面固定不动，只换完稿。整套角色可以共用同一种风格，到了项目后期要换风格，也不必重画任何一张。

## 降低 AI 感

生成的图常带着一眼就能认出的 AI 味：处处一样精细、喷枪般的渐变、多余的光泽和噪点。重新完稿用一种统一、刻意的手工技法取代这些痕迹：赛璐璐的平涂、水彩的晕染、版画的线条。如果只想保留原本的样子、清掉这些痕迹，就用去 AI 感（轻、重）完稿。

完稿改的是上色，不是画面本身。构图、细节密度和光线带来的 AI 感，要在生成时就避免（见 [source-spec.md](skills/refinish/references/source-spec.md)）。它也不会隐藏图片的来源：生成的图经过完稿仍然是生成的，平台要求披露的，照样要披露。

## 改什么，不改什么

| | |
|---|---|
| **会改** | 线条的粗细、颜色和质感；阴影的形状和层次数；高光；配色和光线，包括夜晚和黄昏；画材（颜料、纸、墨、网点、像素） |
| **不改** | 比例、眼睛的画法、姿势、衣褶、构图 |

第二行是有意为之。如果你想要的是"按另一位画师的方式画脸"，这不是那类工具；如果你想让自己的画，按动画上色部门、版画工坊或像素画师的方式完稿，那它正合适。

## 完稿方式

<p align="center">
  <img src="docs/images/styles.jpg" alt="示例角色的 34 种完稿，按类别排列：动画赛璐璐、干净的完稿、双色印刷、绘画、版画与线稿、像素、特殊技法">
</p>

| 类别 | 完稿方式 |
|---|---|
| 动画赛璐璐 | 电视动画、浓重、粗墨线、剧场版日常、剧场版夜景、粉彩剧场版、90 年代、电视夜景、电视黄昏 |
| 干净的完稿 | 去 AI 感（轻、重）：保留原图的颜色和线条，去掉渲染噪点和喷枪渐变 |
| 双色与少色印刷 | 原图自身的两种颜色、藏青双色、双色印刷、怀旧棕、蓝晒、Riso 孔版印刷 |
| 绘画 | 水彩、水粉、厚涂 |
| 版画与线稿 | 漫画网点、动画原画、丝网印刷 |
| 特殊技法 | 水墨、浮世绘木版、波普艺术网点、霓虹灯、彩绘玻璃、剪纸、炭笔、色粉、贴纸 |
| 像素 | 96 px 角色、192 px 头像 |
| 风景 | 木版、水墨、水彩风景 |

每种完稿在 [presets.md](skills/refinish/references/presets.md) 里都有说明：需要什么、原图怎样准备最好、做不到的地方。

## 背景与场景

背景的处理方式不同。手绘背景线条少，大部分是长渐变（天空、雾气、慢慢暗下去的室内），赛璐璐的平涂色阶会把这些渐变切成一块一块。动画本来也不用赛璐璐画背景：赛璐璐是角色，叠在手绘背景上。

所以背景用干净的去 AI 感完稿或风景完稿，角色用赛璐璐完稿叠在上面。`composite.py` 负责把两者合成，加上景深、光线包裹，以及让两者处在同一种光线下的调色。

画在场景里的角色，可以先用 `cutout.py` 抠出来：画一圈大致的外框，精确的边缘交给颜色判断，同时还能拿到补好角色位置的背景，可以单独完稿。

## 不只是滤镜

- **按部位处理，而不是按像素。** 主体文件（subject file）标出图中每个部位是什么：皮肤、头发、每件衣服。每种材质都用它自己的颜色上色，红色缎带不会渗进旁边的皮肤。主体文件会自动生成草稿，再用几个提示点修正。
- **每张结果都会检查。** 每次完稿都和原图对比：部位、颜色、外框、丢失的五官细节、被印成别的颜色的皮肤、脸部周围的方框、深色布料上的斑块。每条警告都会指出位置和可能的原因。
- **对照参考图。** `fit_style.py` 测量参考图的完稿（线条深浅、饱和度、平涂程度、边缘柔和度、颗粒感），从赛璐璐系的风格一轮一轮调出相符的版本。参考图只测量，不复制。设计（比例、眼睛画法）和场景光线不会带过来；参考图若是其他技法，就从最接近的内置风格开始，再用文字微调（`tweak_style.py`）。
- **用文字调整。** `tweak_style.py` 把"阴影柔和一点""再鲜艳一点""線を太く"这类说法转换成参数步骤，并告诉你哪个测量值应该随之变化。
- **改变时段。** 夜晚和黄昏由白天的颜色在线性光下推算，或者套用电影感的夜景调色。
- **混合完稿。** `recipe.py` 按部位叠加完稿：衣服用水彩、脸用赛璐璐，或在水彩上以正片叠底叠一层网点。
- **修复原图。** `repair.py` 修正抠图留下的白边、杂点、线稿断口、越过材质边界的渗色，而且不改画风。

## 实际表现

下面的数字来自项目自己的测试，用的是代码没见过的图（这些图不在仓库里）：开图前先冻结代码、写好通过标准；看过的图之后只用于开发。

- **部位。** 在两组新角色上，配合 agent 的提示点，41 张中有 39 张在两轮内所有部位都正确。
- **37 种完稿用在 16 个新角色上**（10 个肤色较深，4 个是柔和的喷枪上色），21 种完稿通过了全部测量：
  - 除黄昏和 90 年代以外的所有赛璐璐完稿；
  - 两种去 AI 感完稿；
  - 绘画类完稿；
  - 彩绘玻璃、剪纸和贴纸。

  所有完稿都没有在深色布料上留下斑块。
- **还没做好的地方。** 以下问题都列在[更新日志](CHANGELOG.md)中，尚待修正：
  - 漫画网点会把较深的肤色印得太浅；
  - 波普艺术仍会在脸周围留下方框；
  - 浮世绘木版会把小麦色皮肤印淡；
  - 柔和喷枪上色的原图，在所有平涂类完稿下阴影边缘都会破碎。
- **与真品对比。** 木版、水彩、水墨完稿与博物馆的公有领域扫描图比较过纸色、最深的墨色、平涂面积和边缘加深。

## 安装

**Claude Code**

```
/plugin marketplace add owoevan-dev/refinish-skill
/plugin install refinish-skill@refinish-skill
```

**其他 agent**

把 `skills/refinish` 复制或链接到 agent 的 skills 文件夹，或者使用 [skills.sh](https://skills.sh)：

```
npx skills add owoevan-dev/refinish-skill
```

脚本需要 Python 3.10 及以上版本，以及 `numpy`、`opencv-python`、`scipy`（`Pillow` 可选）。不需要 GPU、网络，也不用下载模型。

## 使用方法

装好 skill 之后，直接用平常的话让 agent 处理：

> 把 `sprites/` 里的图都改成电视动画赛璐璐，每张风格要统一。

> 这张立绘 AI 感太重，帮我处理干净，颜色保持不变。

> 把 `street.png` 里的女孩抠出来，改成 90 年代赛璐璐，再放回原位。

agent 会按 [SKILL.md](skills/refinish/SKILL.md) 的流程：先检查原图、建立主体文件、执行完稿，自己看过结果再交给你。脚本也可以单独使用：

```bash
python skills/refinish/scripts/check_input.py source.png
python skills/refinish/scripts/prep.py source.png image.png --scale 2
python skills/refinish/scripts/auto_parts.py image.png subject.json --upscaled 2
python skills/refinish/scripts/refinish.py subject.json tv-cel out.png
```

## 局限

- 不改设计。比例、脸、姿势和衣褶都来自原图。
- 部位不一定一次就拆对。干净的赛璐璐图在两轮提示点内大多会正确；半写实、密集花纹、黑上黑这类比较难。拆不好时，agent 会请你用一句话说明哪里不对，再自己修改提示点；还是不行，就合并部位、只完稿拆对的部分，或改用不需要部位的完稿（[subject-file.md](skills/refinish/references/subject-file.md)）。
- 柔和的喷枪上色让平涂类的赛璐璐完稿较难处理，绘画类完稿更能应付。[source-spec.md](skills/refinish/references/source-spec.md) 说明了怎样让图像模型画出容易完稿的图。
- 抠图是硬边。面纱、镜片、烟雾，要么整块算角色，要么整块算背景。
- 不会隐藏图片的来源。AI 生成的图经过任何完稿（包括去 AI 感）仍然是 AI 生成的，这些完稿也没有针对任何检测工具做调整。

## 文档

| | |
|---|---|
| [SKILL.md](skills/refinish/SKILL.md) | agent 遵循的流程，以及每个脚本 |
| [presets.md](skills/refinish/references/presets.md) | 全部 37 种完稿：各自需要什么、如何准备、有哪些局限 |
| [subject-file.md](skills/refinish/references/subject-file.md) | 部位、提示点，以及实测到的失败情况 |
| [adjusting.md](skills/refinish/references/adjusting.md) | 看起来不对时该改什么 |
| [cutout.md](skills/refinish/references/cutout.md) | 从场景中抠出角色，再放回原位 |
| [compositing.md](skills/refinish/references/compositing.md) | 背景、景深和光线包裹 |
| [style-format.md](skills/refinish/references/style-format.md) | 编写或修改风格文件 |
| [legal-and-disclosure.md](skills/refinish/references/legal-and-disclosure.md) | 画风与著作权，以及 Steam 和 pixiv 的要求 |

文档正文以英文撰写。

## 参与贡献

欢迎通过 [Issues](https://github.com/owoevan-dev/refinish-skill/issues) 报告问题或提出新的完稿方式。目前不接受外部的 pull request，原因和替代做法写在 [CONTRIBUTING.md](CONTRIBUTING.md) 里。

## 许可证

[MIT](LICENSE)。上方图片中的示例角色，是为这份 README 用图像模型生成的；图中所有完稿都是这个 skill 的输出。skill 的 `evals` 文件夹中的测试图由代码绘制；标志的文字是 Noto Serif TC（SIL Open Font License）转成的轮廓。
