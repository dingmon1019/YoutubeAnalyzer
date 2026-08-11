<div align="center">

# 🎬 tuto

**유튜브 튜토리얼을 "따라 할 수 있는 문서"로 바꾸는 Claude Code 플러그인**

*Turn any YouTube tutorial into a verified, step-by-step guide.*

[![Version](https://img.shields.io/badge/version-0.1.6-blue.svg)](https://github.com/dingmon1019/YoutubeAnalyzer/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-101%20passed-brightgreen.svg)](tests/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2.svg)](https://claude.com/claude-code)
[![Languages](https://img.shields.io/badge/video-KO%20%7C%20EN-orange.svg)](#)

```
/tuto https://youtu.be/VIDEO_ID
```

</div>

---

## ✨ 무엇을 하나 · What it does

영상의 **설정값·버튼명·조작 순서**를 자막이 아니라 **화면에서 직접 읽어** 스텝별 가이드를 만듭니다.
모든 값에는 근거 프레임 타임스탬프가 붙고, **독립 감사 에이전트가 반박을 시도한 뒤에야** 제시됩니다.

> *Reads settings, button labels and operation order **from the screen** — not from captions.
> Every claim carries a source-frame timestamp and must survive **independent adversarial audit agents**
> that are asked to refute it.*

---

## 📊 숫자로 보는 성능 · By the numbers

<div align="center">

| 지표 · Metric | 값 · Value | 무슨 뜻인가 · What it means |
|---|:---:|---|
| **값 환각** · Hallucinated values | **0건** | 골든셋 검증에서 지어낸 값 0개 · Precision **1.000** |
| **스텝 재현율** · Step recall (R1) | **0.913** | 정답지 23스텝 중 21개 포착 |
| **값 정확도** · Value F1 | **0.909** | 설정값·버튼명·수치 일치도 |
| **오케스트레이터 이미지 비용** | **−95%** | `cache_write` 432,788 → 21,594 |
| **파이프라인 총비용** | **−27%** | 19분 영상 기준 3.35M → 2.44M 토큰 |
| **다운로드·분석 속도** | **8.1×** | 154초 → 19초 |
| **확대 추출 속도** | **5.4×** | 327초 → 61초 |
| **감사 에스컬레이션률** | **0%** | 채택 모델 기준 재검 필요 0건 |
| **테스트** · Tests | **101** | 전부 통과 |

</div>

---

## 🎯 왜 정확한가 · Why it's accurate

튜토리얼에서 **정작 중요한 값은 말로 하지 않습니다. 화면에만 있습니다.**

> *The values that matter are usually **never spoken** — they only exist on screen.*

실제로 겪은 사례입니다 · Real cases from measured runs:

| 자막이 말한 것 · Caption said | 화면에 있던 것 · Screen showed |
|---|---|
| "윈도우는 `python`" | **`python3`** — 사용자 실측 결과 화면이 맞았음 |
| "슬로우다운 **98배**" | **`0.98배`** — 한국어 ASR이 소수점 누락 |
| "**16배** 차이" | **`16.3x`** — 90,991 vs 5,584 |
| "**600** 팔로워" | **`576`** |
| `irresistible` | **`irresistable`** — 화면 원문 오타, 고쳐 쓰지 않음 |

**자막과 화면이 다르면 화면을 채택**하고 불일치를 각주로 남깁니다.
화면에서도 읽히지 않으면 **추측하지 않고** `⚠️ 화면 확인 필요`로 표시합니다.

> *When caption and screen disagree, the screen wins and the conflict is footnoted.
> When neither is legible, it prints `⚠️ needs visual check` instead of guessing.*

### 감사가 실제로 잡아낸 것 · What the audits actually caught

| 결함 · Defect | 어떻게 잡았나 · How |
|---|---|
| 존재하지 않는 연출을 서술 (프레임 이중 오귀속) | SSIM 실측 11쌍 — 동일 0.994 vs 별개 0.634로 규명 |
| `83K` → 실제 **`84K`** | 원본 영상 네이티브 해상도 재추출 + 22× 확대 |
| "평균 조회수 13.1배" → 실제 **"vs the 19 no-ask posts"** | 분모 누락 검출, 요약↔본문 내부 불일치 |
| 슬라이드가 스스로 모순 (`20,542` vs `21,022`) | 같은 슬라이드 본문 산수(576 + 19,966)로 해소 |
| 표 빈칸을 자막으로 메움 | 화면엔 아이콘만 → `(아이콘만)` + `자막 출처:` 분리 |

---

## 🚀 설치 · Install

```bash
claude plugin marketplace add dingmon1019/YoutubeAnalyzer
```
```bash
claude plugin install tuto@yta
```

재시작하면 `/tuto`가 스킬 목록에 나타납니다. · *Restart Claude Code, then `/tuto` appears.*

**업데이트** · Update — `install`은 이미 설치된 플러그인에 동작하지 않습니다:

```bash
claude plugin update tuto@yta
```

<details>
<summary><b>요구사항 · Requirements</b></summary>

<br>

| | 설치 예시 · Example |
|---|---|
| Python 3.11+ | — |
| ffmpeg / ffprobe | `winget install Gyan.FFmpeg` · `brew install ffmpeg` |
| yt-dlp | `pip install -U yt-dlp` |
| *(선택 · optional)* faster-whisper | `pip install faster-whisper` |

세션에서 `/tuto`를 처음 호출하면 프리플라이트가 자동 점검하고 빠진 항목의 설치 명령을 안내합니다.
*A preflight check runs on first use and tells you exactly what to install.*

</details>

<details>
<summary><b>설정 · Configuration (선택 · optional)</b></summary>

<br>

자막이 **아예 없는** 영상만 ASR이 필요합니다. `~/.config/yta/.env`가 첫 실행 시 자동 생성됩니다.

```ini
GROQ_API_KEY=          # console.groq.com/keys
CACHE_MAX_VIDEOS=10    # LRU: video.mp4를 유지할 최대 영상 수
```

키가 없어도 동작합니다 — **Groq → 로컬 whisper → 프레임 중심 분석** 순으로 자동 폴백합니다.
*Works without a key: falls back Groq → local whisper → frame-only analysis.*

</details>

---

## 📖 사용법 · Usage

```
/tuto https://youtu.be/VIDEO_ID
/tuto https://youtu.be/VIDEO_ID 파이썬 PATH 체크하는 부분만 알려줘
```

질문을 함께 주면 가이드를 만든 뒤 **그 질문에 먼저** 답합니다.
같은 세션의 후속 질문은 **재다운로드 없이** 캐시된 프레임·자막으로 답합니다.

> *Pass a question and it answers that first. Follow-ups reuse cached frames — no re-download.*

산출물 · Output → `~/.yta/cache/<video_id>/guide.md`

<details>
<summary><b>산출물 예시 · Sample output</b></summary>

<br>

```markdown
## 스텝 4: 설치 실행 — Add Python to PATH 체크 + Install Now (02:56–04:05)

1. 설치 파일 실행 → 다이얼로그 "Install Python 3.9.6 (64-bit)",
   기본 경로 `...\AppData\Local\Programs\Python\Python39` (t=03:23)
2. 체크박스 2개 — "Install launcher for all users (recommended)" 체크됨 /
   "Add Python 3.9 to PATH" 이 시점 미체크 (t=03:23)
3. ⚠️ PATH 체크 순간·Install Now 클릭 순간은 전환 연출(검은 화면)로
   가려져 프레임에 없음 (t=03:51)

## 감사 스탬프
📋 표본 감사: 6개 주장 중 5 일치, 1 수정 — Sonnet 6건 + 상위 모델 재검 1건 /
커버리지: 누락 2건 보강
```

</details>

---

## 🏗 어떻게 동작하나 · How it works

```
  패스 1 · MAP            패스 2 · ZOOM              작성 · BUILD          검증 · VERIFY
  ─────────────          ──────────────             ────────────         ──────────────
  analyze.py             판독 에이전트               가이드 빌더           표본 감사 ×6
   ├ yt-dlp               → zoom-plan.json           (sonnet)             (독립 컨텍스트)
   ├ 원어 자막 2단계       ├ 자막 지시어 큐            ├ 프레임 판독         ├ "반박하라"
   ├ 히트맵 · 챕터         ├ 챕터 경계                ├ --crop 재확대       ├ 불일치 → 상위 모델
   ├ 활동곡선 피크         ├ 활동 피크 커버           └ guide.md           └ 커버리지 감사
   └ 지도 프레임           └ 프레임 공백 탐지
```

**1️⃣ 신호 가중 프레임 선정** — 등간격이나 장면 전환만으로 자르면 **정지된 문서 화면이 통째로 스킵**됩니다.
그런데 튜토리얼에서 값이 적혀 있는 곳이 바로 그 정지 화면입니다.
유튜브 **히트맵**(많이 본 구간), **챕터 경계**, **활동곡선 피크**(말 없는 조작 방어),
**자막 지시어 큐**("여기 보시면", "클릭", "look here", "this setting")를 겹쳐 배정합니다.

> *Scene-change sampling skips static document screens — exactly where the values live.
> We weight by heatmap, chapter boundaries, activity peaks and caption cue words instead.*

**2️⃣ 해상도 티어링** — 글자를 옮겨 적어야 하는 화면(슬라이드·표·조건식·메뉴·터미널)만 **1024px**,
삽화·토킹헤드는 512px. **지도 프레임으로 못 본 지점은 무조건 1024** — 텍스트가 없다는 걸 확인할 수 없으니까요.

**3️⃣ 프레임 공백 탐지** — 지도 프레임이 60초 이상 비는 구간을 찾아 우선 배정합니다.
튜토리얼의 **"제대로 됐는지 확인하는" 마지막 구간**은 화면 변화가 적어 구조적으로 탈락하는데,
정작 따라 하는 사람에겐 성공 판정 기준입니다. 실측 2건에서 결론부가 통째로 누락된 걸 확인하고 규칙화했습니다.

> *Verification segments at the end of a tutorial are visually static, so samplers drop them —
> yet that's where "did it work?" lives. Gaps ≥60s are detected and prioritized.*

**4️⃣ 독립 반박 감사** — 가이드 본문을 **주지 않고** 주장 1개 + 근거 프레임만 새 에이전트에 보내
*"이 프레임을 읽고 주장을 반박하라"*고 시킵니다. 확증 편향을 구조적으로 차단합니다.
불일치가 나오면 그 주장만 상위 모델로 재검증합니다.

**5️⃣ 커버리지 감사** — 자막·챕터에서 "기대 스텝 체크리스트"를 **먼저** 만들고 가이드와 대조합니다.
표본 감사가 구조적으로 못 잡는 **누락**을 담당합니다.

---

## 📈 어떻게 발전시켰나 · How it evolved

각 라운드는 **"품질 비저하를 증명하지 못하면 롤백"** 규칙으로 진행했습니다.
*Every round had to prove no quality regression — or get rolled back.*

| 라운드 | 한 일 | 실측 결과 |
|:---:|---|---|
| **R1** | 스크립트 병렬화, 감사 모델 3파전 | analyze **8.1×**, zoom **5.4×**, 감사 에스컬레이션 **50% → 0%** |
| **R2** | 커버리지 감사 신설, 서식변화 검증, `--crop` 재확대 | 오류주입 검출 성공 · **OCR은 게이트 미달로 롤백** |
| **R3** | 가이드 작성을 sonnet 빌더에 위임 | 값 **33/33** 동일, 서사 동등 |
| **R4** | 오케스트레이터 컨텍스트에서 **이미지 완전 제거** | `cache_write` **−95%**, 총비용 **−27%**, 품질 순증 |

<details>
<summary><b>💡 남길 만한 교훈 5가지 · Lessons worth keeping</b></summary>

<br>

**OCR은 이 도메인에서 안 됩니다.**
winocr 1024px에서 26개 중 **4개**, tesseract(+kor) **6개**. 게이트 기준 95%에 한참 미달.
영상 압축된 잔글씨는 OCR 불가 도메인이고 VLM 직접 판독이 **70/70**으로 압도적이었습니다. **구현해 놓고 롤백**했습니다.

**검출력 게이트 통과 ≠ 실전 성능.**
저가 모델 감사는 오류주입 **3/3**을 검출했지만 실전에서 `UNVERIFIABLE`·과잉 반박이 쏟아져
에스컬레이션률 **50%**였습니다. 상위 티어는 **0%**.

**선명한 프레임을 받을수록 "빈칸 메우기"가 늘어납니다.**
흐린 프레임은 크롭해 뜯어보느라 빈칸을 알아채지만, 잘 읽히는 프레임은 술술 읽으며 자막으로 메웁니다.
→ 표는 화면 칸 그대로, 빈 칸은 `(아이콘만)`, 자막 출처는 표 밖으로 분리.

**자기보고형 게이트는 보고자가 세지 못한 걸 잡지 못합니다.**
"텍스트 화면 N개 중 N개 1024" 검사가 통과했는데도 오류가 났습니다 — 못 본 화면을 셀 수 없었으니까요.
→ 관측 여부(`observed`)를 산출물에 노출시켜 해결.

**비용 비교는 집계 범위부터 맞춰야 합니다.**
부분 집계와 전체 집계를 비교해 "8.6배 증가"라는 오판을 냈다가, 동일 방법론으로 재측정하니
실제로는 **절반으로 감소**였습니다.

</details>

---

## 🔬 검증 도구 · Evaluation tooling

**비용 집계** · Cost accounting

```bash
python docs/eval/measure-cost.py --marker VIDEO_ID
```

세션 로그에서 실행 1건의 토큰 비용을 본체/서브에이전트로 나눠 집계합니다.
집계 규약(`message.id` dedup, 달러 가중)이 코드에 고정돼 있어 **재현 가능**합니다.

**골든셋 평가** · Golden-set evaluation → [`docs/eval/golden-set-protocol.md`](docs/eval/golden-set-protocol.md)

사용자가 **직접 따라 해 본** 튜토리얼로 정답지를 만들어 회귀 기준으로 씁니다.

- **R1-Recall** — 해야 할 동작을 빠뜨리지 않았는가
- **Value-F1** — **조작값**(따라 하면 내 화면에도 나타나는 것)과 **인용값**(저자 실적 수치)을 분리 집계

---

## ⚠️ 한계 · Limitations

- **≤30분** 영상 기준. 초과 시 구간 지정을 제안합니다. · *≤30 min; longer videos prompt for a range.*
- 조작 튜토리얼이 아닌 **개념 설명형** 영상도 처리되지만, 산출물은 "조작 순서"가 아니라 "슬라이드에 적힌 규칙·수치"입니다.
- 검증하는 것은 **"영상이 말한 것과 화면이 일치하는가"**이지 **"그 내용이 사실인가"**가 아닙니다.
  · *We verify screen↔claim consistency, **not** whether the advice is true.*
- 프레임에 없는 값은 채우지 않습니다. `⚠️`가 남는 건 실패가 아니라 **설계**입니다.
- Windows에서 개발·검증했습니다. macOS/Linux는 경로 처리만 다를 뿐 동작해야 하지만 미검증입니다.

---

## 📚 문서 · Docs

| | |
|---|---|
| [`skills/tuto/SKILL.md`](skills/tuto/SKILL.md) | 오케스트레이션 계약 — 파이프라인 정본 |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | 라운드별 설계 스펙 |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | 구현 플랜 |
| [`docs/eval/`](docs/eval/) | 골든셋 프로토콜 · 비용 집계 도구 |

<details>
<summary><b>캐시 관리 · Cache</b></summary>

<br>

산출물은 `~/.yta/cache/<video_id>/`에 쌓입니다.
`CACHE_MAX_VIDEOS`를 넘으면 오래된 영상부터 `video.mp4`/`audio.mp3`만 지우고 메타데이터·가이드는 남깁니다.

```bash
python skills/tuto/scripts/analyze.py --cleanup
```

</details>

---

## 📄 License

[MIT](LICENSE) © 2026 hwangjs

<div align="center">
<sub>Built as a Claude Code plugin · 101 tests passing</sub>
</div>
