<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-dark-1200.png">
    <img src="assets/brand/logo-1200.png" alt="Refinish" width="440">
  </picture>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <strong>한국어</strong>
</p>

<p align="center">
  <a href="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml"><img src="https://github.com/owoevan-dev/refinish-skill/actions/workflows/tests.yml/badge.svg" alt="테스트"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-1f1c1a" alt="라이선스: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-1f1c1a" alt="Python 3.10 이상">
</p>

<p align="center"><strong>다시 생성하지 말고, 다시 마감하세요.</strong></p>

Refinish는 이미 가지고 있는 그림을 새로 마감하는 [Agent Skill](https://agentskills.io)입니다. 선화, 포즈, 얼굴, 의상 같은 그림 자체는 그대로 두고, 그림자의 모양, 선의 색, 배색, 재료 같은 마감만 다시 칠합니다. TV 애니메이션 셀 채색과 수채화부터 우키요에 목판화, 만화 스크린톤, 픽셀 아트까지 37가지 마감이 들어 있습니다. 생성 이미지 특유의 AI 느낌을 덜어 내는 데에도 쓸 수 있습니다.

모든 처리는 Python(NumPy, OpenCV)으로 하며 이미지 생성 모델은 쓰지 않습니다. 그래서 넣은 캐릭터가 그대로 나옵니다.

<p align="center">
  <img src="docs/images/hero.jpg" alt="한 캐릭터의 여섯 가지 모습: 원본, 수채화, 우키요에 목판화, 만화 스크린톤, 스테인드글라스, 픽셀 아트">
</p>

## 그냥 다시 생성하면 안 되나요?

이미지 생성 모델에 새 화풍으로 다시 그려 달라고 하면 조금 다른 캐릭터가 나옵니다. 얼굴이 조금 바뀌고, 손은 새로 그려지고, 의상 디테일도 어긋납니다. 일러스트 한 장이라면 괜찮을 수도 있습니다. 하지만 서로 맞아야 하는 스탠딩 일러스트 한 세트라면 곤란합니다.

다시 마감하기는 반대로 접근합니다. 그림은 고정해 두고 마감만 바꿉니다. 캐릭터 전원이 같은 룩을 공유할 수 있고, 제작 막바지에 룩을 바꿔도 다시 그릴 그림은 한 장도 없습니다.

## AI 느낌 줄이기

생성 이미지에는 한눈에 알아보는 AI 느낌이 있습니다. 어디나 똑같이 세밀한 디테일, 에어브러시 같은 그러데이션, 과한 광택과 노이즈. 다시 마감하기는 이를 일관되고 의도적인 하나의 수작업 기법으로 바꿉니다. 셀의 평평한 채색, 수채화의 번짐, 판화의 선. 원래 모습은 그대로 두고 흔적만 지우고 싶다면 AI 느낌 제거 마감(약·강)을 쓰세요.

마감이 바꾸는 것은 채색이지 그림 자체가 아닙니다. 구도, 디테일 밀도, 빛에서 오는 AI 느낌은 생성 단계에서 피해야 합니다([source-spec.md](skills/refinish/references/source-spec.md)). 그림의 출처를 숨기지도 않습니다. 생성 이미지는 마감을 거쳐도 생성 이미지이며, 플랫폼이 공개를 요구하는 것은 그대로 공개해야 합니다.

## 바뀌는 것과 바뀌지 않는 것

| | |
|---|---|
| **바뀜** | 선의 굵기·색·질감, 그림자의 모양과 단계 수, 하이라이트, 배색과 빛(밤과 노을 포함), 재료(물감, 종이, 먹, 스크린톤, 픽셀) |
| **그대로** | 비율, 눈을 그리는 방식, 포즈, 옷 주름, 구도 |

두 번째 줄은 의도한 것입니다. 다른 작가가 얼굴을 그리는 방식으로 캐릭터를 그리고 싶다면 이 도구는 맞지 않습니다. 내 그림을 애니메이션 채색 부서, 판화 공방, 픽셀 아티스트가 마감하는 방식으로 마감하고 싶다면 바로 이 도구입니다.

## 마감 종류

<p align="center">
  <img src="docs/images/styles.jpg" alt="샘플 캐릭터의 34가지 마감을 계열별로 배열한 그림: 애니메이션 셀, 깔끔한 마감, 2도 인쇄, 회화, 판화와 선화, 픽셀, 특수 기법">
</p>

| 계열 | 마감 |
|---|---|
| 애니메이션 셀 | TV 애니메이션, 진한 셀, 굵은 선, 극장판 일상, 극장판 밤, 파스텔 극장판, 90년대, TV 밤, TV 노을 |
| 깔끔한 마감 | AI 느낌 제거(약·강): 원래 그림의 색과 선은 살리고 렌더링 노이즈와 에어브러시 그러데이션을 걷어 냄 |
| 2도·소수 잉크 인쇄 | 원래 그림의 두 색, 남색 2도, 2도 인쇄, 세피아, 청사진(사이아노타입), 리소그래프 |
| 회화 | 수채화, 과슈, 두껍게 칠하기 |
| 판화와 선화 | 만화 스크린톤, 애니메이션 원화, 실크스크린 |
| 특수 기법 | 수묵화, 우키요에 목판화, 벤데이 도트 팝아트, 네온사인, 스테인드글라스, 종이 오리기, 목탄, 소프트 파스텔, 스티커 |
| 픽셀 | 96px 캐릭터, 192px 상반신 |
| 풍경 | 목판화, 수묵화, 수채화 풍경 |

[presets.md](skills/refinish/references/presets.md)에 마감마다 무엇이 필요한지, 원본을 어떻게 준비하면 좋은지, 무엇이 어려운지 정리해 두었습니다.

## 배경과 장면

배경은 다르게 다룹니다. 그려진 배경은 선이 적고 하늘, 안개, 어두워지는 실내처럼 긴 그러데이션이 대부분입니다. 셀의 평평한 색면은 이런 그러데이션을 얼룩처럼 끊어 버립니다. 애니메이션도 원래 배경을 셀로 칠하지 않습니다. 셀은 캐릭터이고, 그것을 그려진 배경 위에 겹칩니다.

그래서 배경에는 깔끔한 AI 느낌 제거 마감이나 풍경 마감을 쓰고, 그 위에 셀로 마감한 캐릭터를 올립니다. `composite.py`가 피사계 심도, 라이트 랩, 둘을 같은 빛 안에 두는 색 보정을 더해 합성합니다.

장면 안에 그려진 캐릭터는 먼저 `cutout.py`로 오려 낼 수 있습니다. 대략적인 윤곽을 그리면 정확한 경계는 색이 정합니다. 캐릭터가 있던 자리를 메운 배경도 함께 나오므로 배경만 따로 마감할 수 있습니다.

## 필터와 다른 점

- **픽셀이 아니라 부위 단위로.** 서브젝트 파일에 그림의 각 부위가 무엇인지(피부, 머리카락, 옷 하나하나) 적습니다. 재료마다 그 재료의 색으로 칠하기 때문에 빨간 리본 색이 옆 피부로 번지지 않습니다. 파일은 자동으로 초안이 만들어지고, 힌트 몇 점으로 고칩니다.
- **결과는 매번 검사합니다.** 마감할 때마다 원본과 비교해 부위, 색, 윤곽, 사라진 이목구비, 다른 색으로 찍힌 피부, 얼굴 주변의 사각형, 어두운 천의 얼룩을 확인합니다. 경고마다 위치와 예상 원인을 알려 줍니다.
- **참고 이미지에 맞추기.** `fit_style.py`가 참고 이미지의 마감(선의 진하기, 채도, 평탄함, 가장자리의 부드러움, 입자감)을 측정해 여러 차례에 걸쳐 스타일을 맞춥니다. 참고 이미지는 측정만 할 뿐 복사하지 않습니다.
- **말로 조정하기.** `tweak_style.py`는 "그림자를 부드럽게", "더 선명하게", "陰影柔一點", "線を太く" 같은 말을 파라미터 단계로 바꾸고, 어떤 측정값이 움직여야 하는지 알려 줍니다.
- **시간대 바꾸기.** 밤과 노을은 낮의 색에서 선형 광으로 계산하거나, 영화 같은 야간 색 보정을 적용합니다.
- **마감 섞기.** `recipe.py`는 부위별로 마감을 겹칩니다. 옷은 수채화, 얼굴은 셀로 하거나, 수채화 위에 스크린톤을 곱하기로 겹치는 식입니다.
- **원본 고치기.** `repair.py`는 오려 낸 이미지의 테두리 잔상, 잡티, 끊긴 선화, 재료 경계를 넘어 번진 색을 화풍은 그대로 둔 채 고칩니다.

## 실제 성능

모든 변경은 코드가 한 번도 본 적 없는 그림으로 확인합니다. 그림을 열기 전에 코드를 고정하고 합격 기준을 적어 두며, 한 번 본 그림은 개발용으로만 씁니다.

- **부위.** 새 캐릭터 두 세트에서 에이전트의 힌트를 더한 초안은 41장 중 39장이 두 번 안에 모든 부위가 맞았습니다.
- **37가지 마감을 새 캐릭터 16명에게** (피부색이 짙은 10명, 부드러운 에어브러시 채색 4명 포함). 모든 측정을 통과한 마감은 21가지입니다.
  - 노을과 90년대를 제외한 모든 셀 마감
  - AI 느낌 제거 두 가지
  - 회화 계열 마감
  - 스테인드글라스, 종이 오리기, 스티커

  어두운 천에 얼룩을 남긴 마감은 없었습니다.
- **아직 부족한 점.** 아래는 해결되지 않은 문제로, [변경 기록](CHANGELOG.md)에 올려 두었습니다.
  - 만화 스크린톤은 짙은 피부를 너무 옅게 찍습니다
  - 팝아트는 얼굴 주변에 여전히 사각형이 남습니다
  - 우키요에 목판화는 그을린 피부를 밝게 만듭니다
  - 부드러운 에어브러시 채색 원본은 평평한 색면 계열 마감에서 그림자 가장자리가 들쭉날쭉해집니다
- **실물과 비교.** 목판화, 수채화, 수묵화 마감은 박물관의 퍼블릭 도메인 스캔 이미지와 종이 색, 가장 진한 먹색, 평평한 면적, 가장자리가 진해지는 정도를 비교했습니다.

## 설치

**Claude Code**

```
/plugin marketplace add owoevan-dev/refinish-skill
/plugin install refinish-skill@refinish-skill
```

**다른 에이전트**

`skills/refinish`를 에이전트의 skills 폴더에 복사하거나 링크하세요. [skills.sh](https://skills.sh)를 써도 됩니다.

```
npx skills add owoevan-dev/refinish-skill
```

스크립트를 실행하려면 Python 3.10 이상과 `numpy`, `opencv-python`, `scipy`가 필요합니다(`Pillow`는 선택). GPU, 네트워크, 모델 다운로드는 필요 없습니다.

## 사용법

스킬을 설치한 뒤 에이전트에게 평소 말투로 부탁하면 됩니다.

> `sprites/`에 있는 그림을 전부 TV 애니메이션 셀로 마감해 줘. 모두 같은 느낌으로.

> 이 스탠딩 일러스트는 AI 느낌이 너무 강해. 색은 그대로 두고 깔끔하게 정리해 줘.

> `street.png`에서 여자아이를 오려 내서 90년대 셀로 바꾸고 원래 자리에 다시 넣어 줘.

에이전트는 [SKILL.md](skills/refinish/SKILL.md)의 절차를 따릅니다. 그림을 검사하고, 서브젝트 파일을 만들고, 마감을 적용한 뒤 결과를 직접 확인하고 나서 보여 줍니다. 스크립트만 따로 써도 됩니다.

```bash
python skills/refinish/scripts/check_input.py source.png
python skills/refinish/scripts/prep.py source.png image.png --scale 2
python skills/refinish/scripts/auto_parts.py image.png subject.json --upscaled 2
python skills/refinish/scripts/refinish.py subject.json tv-cel out.png
```

## 한계

- 디자인은 바꾸지 않습니다. 비율, 얼굴, 포즈, 옷 주름은 원본 그대로입니다.
- 부위가 한 번에 제대로 나뉘지 않을 수 있습니다. 깔끔한 셀 그림은 힌트 두 번 안에 대부분 맞지만, 반실사 그림, 촘촘한 무늬, 검정 위의 검정은 더 어렵습니다. 잘 나뉘지 않으면 에이전트가 무엇이 잘못됐는지 한 문장으로 물어보고 힌트를 직접 고칩니다. 그래도 안 되면 부위를 합치거나, 제대로 나뉜 부분만 마감하거나, 부위가 필요 없는 마감을 씁니다([subject-file.md](skills/refinish/references/subject-file.md)).
- 부드러운 에어브러시 채색은 평평한 셀 마감이 다루기 어렵고, 회화 계열 마감이 더 잘 대응합니다. 마감하기 좋은 그림을 이미지 생성 모델에 요청하는 방법은 [source-spec.md](skills/refinish/references/source-spec.md)에 있습니다.
- 오려 내기의 경계는 딱딱합니다. 베일, 렌즈, 연기는 전부 캐릭터이거나 전부 배경이 됩니다.
- 그림의 출처를 숨기지 않습니다. 생성 이미지는 어떤 마감(AI 느낌 제거 포함)을 거쳐도 생성 이미지이며, 어떤 마감도 탐지 도구를 피하도록 조정하지 않았습니다.

## 문서

| | |
|---|---|
| [SKILL.md](skills/refinish/SKILL.md) | 에이전트가 따르는 절차와 모든 스크립트 |
| [presets.md](skills/refinish/references/presets.md) | 37가지 마감: 각각 필요한 것, 준비 방법, 한계 |
| [subject-file.md](skills/refinish/references/subject-file.md) | 부위, 힌트, 실제로 측정한 실패 사례 |
| [adjusting.md](skills/refinish/references/adjusting.md) | 결과가 이상할 때 바꿀 설정 |
| [cutout.md](skills/refinish/references/cutout.md) | 장면에서 캐릭터를 오려 내고 다시 넣기 |
| [compositing.md](skills/refinish/references/compositing.md) | 배경, 피사계 심도, 라이트 랩 |
| [style-format.md](skills/refinish/references/style-format.md) | 스타일 파일 작성과 수정 |
| [legal-and-disclosure.md](skills/refinish/references/legal-and-disclosure.md) | 화풍과 저작권, Steam과 pixiv의 요구 사항 |

문서 본문은 영어로 작성되어 있습니다.

## 기여

버그 신고와 새 마감 요청은 [Issues](https://github.com/owoevan-dev/refinish-skill/issues)에서 환영합니다. 외부 풀 리퀘스트는 지금은 받지 않습니다. 이유와 대신할 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)에 있습니다.

## 라이선스

[MIT](LICENSE). 위 그림의 샘플 캐릭터와 거리 풍경은 이 README를 위해 이미지 생성 모델로 만든 것이며, 그림 속 마감은 모두 이 스킬의 출력입니다.
