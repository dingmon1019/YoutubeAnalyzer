<div align="center">

# 🎬 tuto

### Let AI watch YouTube for you.

Turn YouTube videos into **verified working knowledge** for AI agents — transcripts, screen text, slides, UI, charts, numbers, actions, and timestamps.

**유튜브 영상을 직접 보지 않아도 됩니다.**

AI가 대신 영상을 보고, 자막과 화면을 함께 이해하고, 검증된 지식으로 변환합니다.
이후 AI는 그 내용을 설명하거나 질문에 답하고, 현재 작업과 비교하거나 튜토리얼을 따라 할 수 있습니다.

[![Version](https://img.shields.io/badge/version-0.13.0-blue.svg)](https://github.com/dingmon1019/YoutubeAnalyzer/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-352%20passed-brightgreen.svg)](tests/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2.svg)](https://claude.com/claude-code)
[![Languages](https://img.shields.io/badge/video-KO%20%7C%20EN-orange.svg)](#)

```text
/tuto <youtube-url> [자연어 요청]
```

</div>

---

## One interface

모드를 외울 필요가 없습니다. 영상 URL과 하고 싶은 말을 그대로 적으면 됩니다.

```text
/tuto <url> 이 영상 내용을 내가 이해할 수 있게 설명해줘
/tuto <url> 여기서 알려주는 방법과 우리 프로젝트를 비교해서 적용할 점을 찾아줘
/tuto <url> 영상에서 사용한 설정값과 명령어를 정확히 정리해줘
/tuto <url> 이 튜토리얼을 이해한 다음 현재 프로젝트에 적용해줘
```

**요청은 분석 깊이를 바꾸지 않습니다.** "핵심만 알려줘"라고 해도 영상을 얕게 보지 않습니다 —
사용자는 영상을 직접 보지 않으므로 무엇이 빠졌는지 검증할 수 없기 때문입니다.
요청이 바꾸는 것은 **수집한 지식을 어떻게 쓸지**입니다.

> **Separation of concerns**
> `tuto` = eyes + video understanding · calling agent = reasoning + hands

| 산출물 | 용도 |
|---|---|
| **`evidence.json`** | 기계가 읽는 정본 — 근거가 프레임·타임스탬프까지 추적됨 |
| **`video.md`** | 사람이 읽는 문서 — **영상 구조에 맞춰 자율 구성** (고정 템플릿 없음) |

## Why evidence, not summaries

The values that matter in a video are often **never spoken** — they exist only on screen.

| Caption / ASR said | Screen actually showed |
|---|---|
| `python` | **`python3`** — confirmed by a user following along |
| slowdown **98x** | **`0.98x`** — the Korean ASR dropped the decimal point |
| **16x** difference | **`16.3x`** — 90,991 vs. 5,584 |
| **600** followers | **`576`** |
| `irresistible` | **`irresistable`** — the original on-screen typo is preserved |

`tuto` treats the **screen as evidence**. When captions and frames disagree, the frame wins **and the conflict is preserved as structured data** — not buried in prose:

```json
{
  "id": "c1",
  "claim": "훅 A/B 조회수 격차가 16.3배",
  "timestamp": 132.0,
  "evidence": [
    { "source": "frame",      "ref": "v1" },
    { "source": "transcript", "ref": "42" }
  ],
  "conflict": { "transcript": "16배", "screen": "16.3x" },
  "verification": { "status": "unaudited" }
}
```

That `conflict` field is the point. An agent can **programmatically find the gap** between what a presenter claimed and what their own slide showed.

If a value cannot be read safely, `tuto` emits `⚠️ needs visual check` instead of guessing. Transcript evidence and visual evidence are never merged into one source — `"source": "both"` is rejected by the schema.

> **Separation of concerns.** `tuto` answers *what was said and what was on screen*. What it **means for you** is the calling agent's job.

<details>
<summary><b>evidence.json — full structure</b></summary>

<br>

```jsonc
{
  "schema_version": "0.3",
  "video":       { "id", "title", "url", "duration", "channel" },
  "video_type":  { "primary": "tutorial|presentation|interview|lecture|demo|screen-recording|mixed",
                   "confidence": "high|medium|low", "hint": { /* deterministic signal-based hint */ } },
  "provenance":  { "transcript": { "source", "lang", "segments", "dupes_removed" },
                   "signals":    { "heatmap", "chapters", "activity_peaks", "flags" },
                   "frames":     { "map": [ { "file", "t", "res" } ], "zoom": [ ... ] } },
  "segments":         [ { "idx", "start", "end", "transcript" } ],
  "visual_evidence":  [ { "id", "type", "value", "timestamp", "frame", "confidence" } ],
  "claims":           [ { "id", "claim", "evidence", "conflict", "verification" } ],
  "knowledge_items":  [ { "id", "type", "content", "timestamp", "evidence", "verification" } ],
  "gaps":             [ { "start", "end", "reason" } ],
  "flags":            [ ... ]
}
```

Confidence is **never a fabricated number** — the pipeline has no basis for probability estimates, so only `high|medium|low` and `verified|disputed|unverifiable|unaudited` are allowed. `unaudited` is deliberately distinct from `verified`: 표본 감사는 v0.5.0에서 제거됐다(실측: 4편 24건 판정 수정 0건) — 커버리지 감사(haiku)와 결정론적 교차 대조가 검증을 담당한다. No remaining step assigns `verified`, so an `evidence.json` shows `unaudited` on effectively every item — that must not look like passing. See [Limitations](#limitations).

Full spec: [`docs/eval/evidence-schema.md`](docs/eval/evidence-schema.md)

</details>

---

## Quick start

### 1. Add the marketplace

```bash
claude plugin marketplace add dingmon1019/YoutubeAnalyzer
```

### 2. Install tuto

```bash
claude plugin install tuto@yta
```

Restart Claude Code, then run:

```text
/tuto https://youtu.be/VIDEO_ID
```

Or just say what you want:

```text
/tuto https://youtu.be/VIDEO_ID 이 영상에서 가장 중요한 주장 5개와 근거를 알려줘
/tuto https://youtu.be/VIDEO_ID 이 튜토리얼을 우리 프로젝트에 적용해줘
```

Already analyzed? Ask without re-downloading:

```text
"아까 영상에서 16.3x가 무슨 의미였어?"
```

Output:

```text
~/.yta/cache/<video_id>/evidence.json    ← canonical, for agents
~/.yta/cache/<video_id>/video.md         ← human-readable
```

### Update

```bash
claude plugin update tuto@yta
```

<details>
<summary><b>Requirements</b></summary>

<br>

| Requirement | Install example |
|---|---|
| Python 3.11+ | — |
| ffmpeg / ffprobe | `winget install Gyan.FFmpeg` · `brew install ffmpeg` |
| yt-dlp | `pip install -U yt-dlp` |
| optional: faster-whisper | `pip install faster-whisper` |

A preflight check runs on first use and tells you what is missing.

</details>

<details>
<summary><b>Optional configuration</b></summary>

<br>

`~/.config/yta/.env` is created automatically on first use.

```ini
GROQ_API_KEY=          # Only needed for Groq ASR on videos without usable captions
CACHE_MAX_VIDEOS=10    # Maximum cached videos that retain video.mp4
```

No API key is required. Transcript acquisition falls back through native captions → Groq → local Whisper → frame-only analysis.

</details>

---

## What you get

`video.md`의 구조는 영상에 따라 달라집니다. 튜토리얼이면 절차 중심, 강의면 개념 중심으로 조직됩니다. 유튜브 챕터가 **3개 이상**이면 영상 길이와 무관하게 시간순 챕터 절(`### [MM:SS] 챕터 제목`)로 구성되고, 그렇지 않으면 아래처럼 기존 유형별 구성을 따릅니다.

```markdown
## Step 4: Run installer—Add Python to PATH + Install Now (02:56–04:05)

1. Open the installer → "Install Python 3.9.6 (64-bit)".
   Default path: `...\AppData\Local\Programs\Python\Python39` (t=03:23)
2. "Install launcher for all users (recommended)" is checked.
   "Add Python 3.9 to PATH" is unchecked at this frame. (t=03:23)
3. ⚠️ The exact checkbox and click moments are hidden by a transition. (t=03:51)

## Verification stamp
Sample audit: not run — evidence is frame/caption-traceable but not independently audited.
Cross-check: 1 value disagreement flagged (recorded, not re-verified).
Coverage audit (haiku): 1 missing knowledge item recovered.
```

Follow-up questions in the same session reuse cached frames and captions, so the video does not need to be downloaded again.

---

## Measured results

These are measured golden-set and regression-run results, not marketing estimates. The evaluation protocol uses 3–5 user-verified tutorials and is intended for per-video regression diagnosis, not statistical generalization.

**v0.4.0(위임 파이프라인) 기준. v0.8.0(함수형 서브에이전트 — 얇은 오케스트레이터 + 일회용
서브에이전트: 비전 haiku ×2 → 합성 sonnet → 커버리지 haiku, 본체는 분석 중 이미지를 한 장도
Read하지 않음) 실측: 11분 27초 한국어 튜토리얼 1편, sonnet 세션 기준 $1.55~1.65 · api 4~5분
(`MAX_THINKING_TOKENS=0` 환경) — v0.5.0 solo($2.91 · 12.1 min) 대비 -45%. 사고 토큰을
제한하지 않는 환경에서는 회당 +$0.7~0.9 늘어난다 — `MAX_THINKING_TOKENS=0` 설정을
권장하지만(필수 아님) 스킬이 실행 환경을 강제할 수는 없다. 상세는
[`docs/eval/reports/2026-08-18-function-agents.md`](docs/eval/reports/2026-08-18-function-agents.md) 참고.**

| Metric | Result | Meaning |
|---|:---:|---|
| **Hallucinated values** | **0** | Precision **1.000** on the golden set |
| **Tutorial step recall (R1)** | **0.913** | 21 / 23 expected steps recovered on the tutorial golden set |
| **Value F1** | **0.909** | Settings, labels, and numeric values |
| **Orchestrator image cost** | **−95%** | `cache_write` 432,788 → 21,594 on the frame-reading calls |
| **Orchestrator `cache_write`, whole run** | **−76%** | 185,965 → 43,923 raw, same 19-minute video |
| **Total pipeline cost** | **−11%** | 2.82M → 2.50M effective tokens, same video, same window convention |
| **Round 5 builder cost** | **−49%** | 1,382,095 → 698,126 effective tokens (41 → 16 calls), same video |
| **Round 5 total cost** | **−10.4%** | $11.12 → $9.96 billed, same video, orchestrator on `opus` both sides |
| **Download + analysis** | **8.1× faster** | 154s → 19s |
| **Zoom extraction** | **5.4× faster** | 327s → 61s |
| **Audit escalation** | **0%** | On the selected audit model |
| **Tests** | **352 passing** | Current regression suite (`python -m pytest tests/ -q`) |

**Why total cost falls less than `cache_write`:** `cache_read` scales with how much conversation
already precedes the run, not with the pipeline. Between the two measurements above it went
464K → 631K (weighted) purely from session position, absorbing most of the `cache_write` win.
Any cost claim here is therefore a same-video, same-window-convention comparison — see the
re-measurement note in [`docs/eval/measure-cost.py`](docs/eval/measure-cost.py).

**Round 5's builder win was partly clawed back by the orchestrator.** Adding call-count-control
instructions to `SKILL.md` cut builder cost by 49%, but it also grew the orchestrator's own
resident context (`cache_read` per call 82K → 101K, calls 27 → 38, +56% orchestrator cost) —
netting only −10.4% overall instead of the −4~5.5× originally targeted. A model-tier lever
(cheaper orchestrator) was attempted but not adopted: it caused incomplete runs or polling
blowup in this measurement setup. Full trial-and-error log: [`docs/eval/reports/2026-08-18-round5.md`](docs/eval/reports/2026-08-18-round5.md).

**v0.8.0 quality, measured honestly.** Knowledge items landed at 30–36 per run, and hallucinations
stayed at 0. The cost cut was not free, though: reading frames through a disposable `haiku` vision
subagent produces roughly **1 command/setting misspelling per video** — small on-screen text is
genuinely hard for a fast vision pass to read correctly. Cross-check, the `⚠️ needs visual check`
flag, and the coverage audit form a three-layer net that catches some but not all of these — in one
measured run, cross-check flagged a `100`↔`200` value disagreement and a recheck subagent corrected
it before `video.md` was written. That is partial defense, not a fix: sample audits remain unrun
(see [Limitations](#limitations)). Full numbers: [`docs/eval/reports/2026-08-18-function-agents.md`](docs/eval/reports/2026-08-18-function-agents.md).

**v0.9.1 density recovery, measured (same 32-minute video, before/after).** The fixed per-run
budgets above worked well at 11 minutes but quietly starved longer videos: the same 32-minute
tutorial (`tkkbYCajCjM`, 32:22) came out at **33 knowledge items (0.9/min)** under the old flat
caps. Making the map, zoom, and knowledge budgets scale with duration (see
[Duration-proportional budgets](#6-duration-proportional-budgets)) brought the same video to
**76 items (2.35/min)** — back in range with the 11-minute baseline (2.7/min) — with unobserved
gaps down from **15 to 0** and `video.md` rendering as **24 chapter sections**. Cost came out to
**$3.77** (**$0.117/min**, cheaper per minute than the 11-minute video's ~$0.14/min) — **$0.0496
per knowledge item**, under the $0.05 reference target. The 11-minute baseline is unchanged by this
work ($1.55–1.65, 30–36 knowledge items). Full numbers:
[`docs/eval/reports/2026-08-19-long-video.md`](docs/eval/reports/2026-08-19-long-video.md).

**v0.11.0 gap-targeted backfill, measured (50:38 Docker code-along tutorial).** The backfill
stage recovered information that existed only on screen and never in captions: the backend
Dockerfile in full (`FROM python:3.12-slim` … `CMD ["uvicorn", ...]`), the `/bin/bash` argument
to `docker exec`, and the frontend Dockerfile. Confabulation held at **0** — all 3 recovered
frames were checked directly against the source frames. Cost rises **roughly $1–2** when the
stage triggers; the measured run came to **$5.72** under the prior 16-frame cap. The cap has
since been lowered to 12 frames, which is estimated (**not yet remeasured**) at **$4.6–4.9**.
Full numbers: [`docs/eval/reports/2026-08-19-gap-backfill.md`](docs/eval/reports/2026-08-19-gap-backfill.md).

**v0.13.0 selective registration, measured (`kYPAlvnRiiI`, 20:04 tutorial, before/after).**
Registering only the observations that `knowledge_items`/`claims` actually cite — instead of
copying every V-line into `evidence.json` — cut cost from **$5.17 to $2.98 (−42%)**, with
registered V dropping **155 → 21**. A separate 2-minute integration gate completed end-to-end
with 0 uncited registrations. The knowledge-retention gate (≥85% of a baseline, i.e. 44 items)
missed at **37 items (71%)**; a **$0.4** root-cause isolation experiment — re-running only
synthesis on the same input with a step-merging-prohibition fix — reproduced the same 35
knowledge items, tracing the shortfall to upstream transcript-density variance rather than to
the registration change itself: the same video's zoom transcript came out at **125 lines on
scout vs. 42 lines on the main gate**, a pre-existing condition (present since v0.11.0) unrelated
to this branch. The merge was approved on that basis; transcript-density variance is now tracked
as an open limitation (see [Limitations](#limitations)) instead of fixed here. Full numbers:
[`docs/eval/reports/2026-08-21-selective-reg.md`](docs/eval/reports/2026-08-21-selective-reg.md).

See [`docs/eval/`](docs/eval/) for the evaluation protocol and cost-accounting tool.

---

## How it works

```text
MAP                     VISION① (sonnet)        ZOOM                    VISION② (sonnet)        SYNTHESIZE (sonnet)     CROSS-CHECK             COVERAGE (haiku)        RENDER
──────────              ──────────              ──────────              ──────────              ──────────              ──────────              ──────────              ──────────
analyze.py              transcribe.md           zoom.py                 transcribe.md           synthesize.md           evidence.py             digest+pass1 only       evidence.py
├ yt-dlp                ├ map frames 병렬 Read  ├ 1 call only           ├ zoom frames Read      ├ 이미지 Read 금지      ├ --from-lines          ├ no image Read         ├ --render
├ captions              ├ V라인 (화면 전사)     ├ 4×1024 max            └ V라인 (전사)          ├ 자막+V라인 텍스트만   ├ --cross-check         └ gaps → merge          ├ single Write
├ heatmap               └ Z라인 (확대 요청)     ├ 6 frames total                                ├ 인용 V만 복사          ├ hash/number reread                            ├ free-form structure
├ chapters                                      └ 1 crop max                                    └ + K/C/G 단일 배치     ├ zero extra cost                               ├ (t=MM:SS) refs
├ activity peaks                                                                                                        └ flag 건수만 기록                               └ verification stamp
└ map frames
```

Thin orchestrator, disposable subagents — the orchestrating agent (본체) runs MAP, ZOOM,
CROSS-CHECK, and RENDER itself (script calls and deterministic post-processing), but it never
Reads a video frame during analysis. Frame reading happens twice, inside throwaway vision
subagents (`sonnet` since v0.16.0 — haiku's diligence variance, thin runs of 0.58 V-lines/frame
against healthy runs of 5+, was measured as the dominant quality swing and removed at the source;
a deterministic thin-detection check with one same-model retry remains as a safety net) that
vanish after writing a line-based transcript (V-lines) and, on the map pass, zoom targets
(Z-lines). A third disposable subagent (`sonnet`, text-only — no image access)
synthesizes those transcripts and the caption transcript into knowledge, claims, and conflicts.
The only remaining subagent call is the coverage audit (`haiku`), which never reads images either.

`evidence.json`이 정본이고 `video.md`는 그것을 사람이 읽게 조직한 것입니다.
**문서를 먼저 쓰고 근거를 맞추지 않습니다** — 순서가 바뀌면 문서에 맞춰 근거를 지어내게 됩니다.

### 1. Signal-weighted frame selection

Uniform sampling and scene-change detection can skip static screens—exactly where tutorials often show settings, terminal commands, tables, and configuration values.

`tuto` combines YouTube heatmaps, chapter boundaries, activity peaks, caption cue words such as “click” / “look here,” and frame-gap detection.

### 2. Resolution tiering

Text-heavy frames such as slides, tables, menus, and terminals are extracted at **1024px**; illustrations, transitions, and talking heads use **512px**. Zoom points chosen without map coverage should be requested at 1024px (see SKILL §2). `zoom.py` itself will not process more than 20 high-resolution frames or 60 total frames per call. The orchestrator makes a **single** `zoom.py` call per analysis and keeps it far under that ceiling — a self-imposed budget that now scales with video duration (see [Duration-proportional budgets](#6-duration-proportional-budgets) below), plus at most one `--crop` follow-up.

### 3. Gap detection

Low-motion verification sections near the end of tutorials are easy for samplers to miss —
`tuto` explicitly revisits gaps rather than trusting uniform or scene-change sampling alone. This
rule was added after two measured runs omitted entire conclusion sections. It started as a flat,
always-on 60-second threshold; it is now a duration-gated, activity-targeted stage with its own
measured results — see [Gap-targeted backfill](#7-gap-targeted-backfill) below.

### 4. Deterministic cross-check

Per-claim adversarial sample audits — a fresh agent independently trying to refute a sampled subset of claims — were removed in v0.5.0: 표본 감사는 v0.5.0에서 제거됐다(실측: 4편 24건 판정 수정 0건) — 커버리지 감사(haiku)와 결정론적 교차 대조가 검증을 담당한다.

`evidence.py --cross-check` re-reads hashed and numeric values across `visual_evidence`, `claims`, and `knowledge_items` looking for internal disagreement — at **zero additional cost**, since it is deterministic post-processing rather than a subagent call. Through v0.11.0, frames it flagged were re-read once by a disposable vision subagent (`haiku`) and the value corrected via `merge` before `video.md` was written — this recheck path caught real errors in measurement: an 11-minute video's `100`↔`200` value disagreement, corrected before render; on a 32-minute video, cross-check flagged 9 disagreements, of which 1 was a real misread (`108.00`↔`105.00` KiB/s, corrected) and 8 confirmed the value was already accurate. **As of v0.13.0 the automatic recheck dispatch is removed** — recent flags measured as false positives across the board, so a flag is now recorded as a count only (`--cross-flags`), not re-verified. See [Lenient validation contract](#9-lenient-validation-contract).

Cross-check cannot catch a reading that is wrong but internally *consistent* — a value nobody disagreed with is not the same as a value someone independently verified. That gap is why `verification.status` defaults to, and effectively stays at, `unaudited` (see [Limitations](#limitations)).

### 5. Coverage audit

Coverage audit builds an **expected knowledge checklist** from the source and compares it against **`claims` and `knowledge_items` in `evidence.json`** — not against document headings.

An adaptive `video.md` heading like `## Phase 1` says nothing about what it contains, and `evidence.json` is the canonical source anyway. So completeness is checked as `source → evidence` first, and `evidence → video.md` second.

It is the pipeline's **only** subagent call, and it runs on `haiku`: it receives `evidence.py --coverage-input` (a digest of `claims`/`knowledge_items`) plus the `pass1-report.txt` transcript — **text only, image reads are explicitly forbidden in its prompt.** It is asked what a viewer of the transcript would expect to know that the digest does not already contain, not asked to re-derive values from frames. Candidates it returns are checked against the transcript before being merged in — coverage audit proposes gaps, it does not write them unconfirmed.

### 6. Duration-proportional budgets

Fixed per-run ceilings quietly starved long videos: a 32-minute tutorial measured against the same
map-frame and knowledge caps as the 11-minute regression baseline came out at roughly a third of
the knowledge density (0.9 items/min vs. 2.7). Budgets now scale with video length instead of a
flat number:

| Resource | ≤20 min | 20 min+ |
|---|---|---|
| Map frames | 0.7/min (unchanged) | 1.0/min, capped at 34 |
| Zoom targets | up to 4 | 6–8 |
| Knowledge items | up to 30 (unchanged) | 2.5/min ceiling, 1.5/min floor target |

**A ceiling alone did not raise density.** Allowing up to 2.5 knowledge items/min still left the
model stopping at 40 items on a 32-minute video — a ceiling caps runaway extraction, it does not
tell the model to keep extracting. Adding an explicit **1.5 items/min floor as a target** moved the
same video to 76 items (2.35/min) on the next run. See [Measured results](#measured-results) for
the full before/after.

### 7. Gap-targeted backfill

Videos over 20 minutes get one more pass after the standard pipeline. `evidence.py --gap-plan`
computes gaps over **90 seconds** deterministically from frame timestamps — both this threshold
and the 20-minute trigger are enforced in code, not in prose, so shorter videos incur no extra
cost. Each gap is targeted at its **activity-signal peak** rather than its midpoint, and the
result is capped at **12 frames**, longest gaps first if that cap would be exceeded.

Those frames are then transcribed **blind** — the transcription pass receives the frame paths but
not the caption transcript, so it has no caption context to backfill screen content from. This is
a structural defense against confabulation: the same model that fabricated two values when given
captions produced zero fabrications once captions were withheld (see
[Measured results](#measured-results)). The result is checked against the existing knowledge
digest, and only new items are merged in.

Activity-signal targeting still misses **quiet screens** — scenes with typing but little visual
change or verbal cue, such as editing a `.env` file. See [Limitations](#limitations).

### 8. Selective registration

검수(비전 서브에이전트가 프레임을 읽는 것)는 이전과 동일하게 **전량** 수행된다 — 줄어드는
것은 **등재**뿐이다. `synthesize.md`는 이제 `vision-*.lines`의 V라인을 전부 patch로
옮기지 않고, `knowledge_items`/`claims`가 `refs`로 실제 인용하는 V만 옮긴다(`v#`는 patch
내 등장 순서로 재부여). 인용되지 않은 관측은 버려지지 않는다 — 원본 `vision-*.lines`가
캐시(`<cache_dir>/`)에 그대로 남아, 정본(`evidence.json`)에 없는 관측을 묻는 후속 질문이
오면 그때 Read해 지연 로딩한다.

측정(20분 튜토리얼, 도입 전 → 후): 비용 **$5.17 → $2.98(−42%)**, 등재된 V **155 → 21**.
자세한 수치는 [Measured results](#measured-results) 참고.

### 9. Lenient validation contract

`evidence.py --from-lines`는 더 이상 낱줄(T/V/K/C/G) 하나의 형식 오류로 배치 전체를
거부하지 않는다. 알 수 없는 레코드 종류만 여전히 즉시 거부하고(스키마 자체가 다르다는
신호이기 때문), 파싱 가능한 필드가 부족한 낱줄은 **드롭 + 카운트**해 stdout에
`MERGED ... DROPPED n`으로 보고한다(재전달 대상이 아닌 정보성 보고 — 이전에는 전량 거부가
재시도 스파이럴로 번졌다). `knowledge_items`/`claims`만 드롭율이 **20%**(`KC_DROP_RATE_GATE`)를
넘을 때 배치 전체를 `INVALID`로 거부한다 — 이 둘이 실제 지식을 나르고, 드롭율이 높다는 것은
산발적 오타가 아니라 파일 전체가 잘못된 규약이라는 신호이기 때문이다. 교차 대조가 남기는
flag도 같은 정책으로 단순화됐다: 비전 서브에이전트를 다시 불러 재판독시키던 루프는 폐지되고
건수만 `--cross-flags`에 기록된다(최근 flag가 전부 오탐으로 측정됨 — [교차 대조](#4-deterministic-cross-check) 참고).

철학: **완전성 > 문자 정밀도 — 오타는 허용하되, 날조는 구조(blind 전사, [§7](#7-gap-targeted-backfill))로
차단한다.** 이 관용은 형식 오류에만 적용된다 — 절차 단계를 합치거나 누락하는 것은 관용
대상이 아니다. `synthesize.md`는 "따라하기 절차의 단계는 합치지 마라 — 단계 하나가 K
하나다"를 명시한다(같은 사실의 재표현만 병합 허용).

**부수 버그 수정.** 관용 드롭이 v-id에 결번을 남길 수 있게 되면서(예: v1·v3 생존, v2
드롭) 다음 배치의 id 오프셋을 `len(visual_evidence)`로 계산하던 기존 로직이 이미 존재하는
id와 충돌하는 버그가 드러났다 — 오프셋 계산을 "기존 v-id 중 최대 숫자" 기준으로 교체해
수정했다.

---

## What the audits have caught

| Defect | How it was resolved |
|---|---|
| Non-existent visual effect caused by double frame attribution | SSIM across 11 frame pairs separated same frames (**0.994**) from distinct frames (**0.634**) |
| `83K` misread as the true value | Native-resolution re-extraction + 22× crop showed **`84K`** |
| “13.1× average views” missing its denominator | Summary ↔ body consistency check recovered **“vs the 19 no-ask posts”** |
| Slide contradicted itself (`20,542` vs. `21,022`) | Same-slide arithmetic (`576 + 19,966`) exposed the inconsistency |
| Empty table cell filled from captions | Output now preserves `(icon only)` / `(아이콘만)` and separates `Caption source:` / `자막 출처:` evidence |

---

## How it evolved

Every round had to demonstrate no quality regression or be rolled back.

| Round | Change | Measured result |
|:---:|---|---|
| **R1** | Parallelized scripts; compared three audit models | Analysis **8.1×** faster, zoom **5.4×** faster, audit escalation **50% → 0%** |
| **R2** | Added coverage audit, formatting/state-change checks, and crop-based re-reading | Injected errors detected; **OCR missed its gate and was rolled back** |
| **R3** | Delegated guide construction to a Sonnet builder | Values remained **33/33** identical; narrative quality remained equivalent |
| **R4** | Removed images from the orchestrator context | `cache_write` **−95%** on frame-reading calls (**−76%** across the whole run), total cost **−11%**, with a net quality improvement |
| **R5** | Cut subagent call counts (parallel reads, single write, fewer crop/audit rounds); measured whether sample audits earn their cost | Builder cost **−49%** (41 → 16 calls); total cost **−10.4%** (orchestrator cost grew **+56%**, absorbing most of the builder win); sample audit fixed at 3 items after injected-error testing showed no detection-power loss vs. 6 |
| **R6 (solo)** | Removed delegation entirely — the orchestrator runs MAP through CROSS-CHECK itself instead of handing frame-reading and document-writing to separate agents; removed sample audits, leaving deterministic cross-check plus a single `haiku` coverage-audit call as the only verification | Sample audits corrected **0 / 24** verdicts across 4 videos before removal — basis for cutting them; solo cost/time: **$2.91 · 12.1 min (opus session, measured 2026-08-18; $1.5 target missed, accepted)** — see [Measured results](#measured-results) |
| **R7 (function-agents, v0.8.0)** | Went the opposite direction from solo — split the single context back into disposable subagents, but this time the orchestrator itself never reads a frame: two `haiku` vision passes read map/zoom frames and vanish, a text-only `sonnet` pass synthesizes knowledge, `haiku` audits coverage, thinking capped to 0 across the whole run | Converged at **$1.55~1.65** (`sonnet` session, `MAX_THINKING_TOKENS=0`), api time **4~5 min** — solo ($2.91) 대비 **-45%**; knowledge 30~36 items, hallucinations 0. Cost gate (≤$1.5) missed by **+3~10%** but accepted by the user; misread gate (0) also missed — **~1 command-spelling misread per video** persisted (small on-screen text) and was accepted as a known limitation — see [Measured results](#measured-results) and [`docs/eval/reports/2026-08-18-function-agents.md`](docs/eval/reports/2026-08-18-function-agents.md) |
| **R8 (long-video, v0.9.1)** | Fixed per-run caps were starving videos over 20 minutes — made map, zoom, and knowledge budgets scale with duration instead of a flat number, and made `video.md` render as chronological chapter sections when the source has 3+ chapters, regardless of video length | Same 32-minute video: knowledge **33 → 76 items** (0.9 → 2.35/min, back in range with the 11-minute baseline), gaps **15 → 0**, **24 chapter sections**; cost **$3.77** (+7.7% over the $3.50 gate, but cheaper per minute than the 11-minute video); 11-minute baseline unchanged — see [Measured results](#measured-results) and [`docs/eval/reports/2026-08-19-long-video.md`](docs/eval/reports/2026-08-19-long-video.md) |
| **R9 (gap-backfill, v0.11.0)** | Added a gap-targeted backfill stage for videos over 20 minutes — deterministic frame-timestamp arithmetic finds gaps over 90 seconds (code-gated, so shorter videos are unaffected), targets each gap's activity-signal peak instead of its midpoint, caps the result at 12 frames, and transcribes those frames **blind** (no captions given) | 50-minute Docker code-along tutorial: recovered the full backend Dockerfile, the `docker exec` `/bin/bash` argument, and the frontend Dockerfile — all screen-only, missing from captions. Confabulation **0/3** (frames verified directly). Cost **+$1–2** when the stage triggers ($5.72 measured at the prior 16-frame cap; **$4.6–4.9 estimated, unmeasured** at the current 12-frame cap) — see [`docs/eval/reports/2026-08-19-gap-backfill.md`](docs/eval/reports/2026-08-19-gap-backfill.md) |
| **R10 (selective-reg, v0.13.0)** | Registered only the observations `knowledge_items`/`claims` actually cite instead of copying every V-line, added a lenient format-drop contract for T/V/K/C/G lines (reject-the-whole-batch → drop + count, gated only on a K/C drop rate over 20%), fixed an id-offset bug the lenient drop surfaced, and replaced cross-check's automatic recheck dispatch with count-only flag recording | 20-minute video: cost **$5.17 → $2.98 (−42%)**, registered V **155 → 21**; knowledge-retention gate missed (37/44, 71%) but a **$0.4** isolation experiment traced the shortfall to upstream transcript-density variance (125↔42 lines, same video) rather than to the registration change — merged on that basis, variance tracked as an open limitation — see [Measured results](#measured-results) and [`docs/eval/reports/2026-08-21-selective-reg.md`](docs/eval/reports/2026-08-21-selective-reg.md) |
| **R12 (density-cure, v0.16.0)** | Replaced both vision passes' first attempt with `sonnet` (thin-detection + one retry kept as a safety net) and harmonized the knowledge ceiling to `max(30, 2.5/min)` — four back-to-back runs of the same 13-minute video had shown haiku's first pass was pure double-payment when thin (both passes thin → 4 dispatches + 2 round-trips) and that K 29–30 was ceiling saturation, not extraction weakness | Same video: **$2.665 · K 36 · zero retries · map density 4.2 V/frame** vs the escalation path's $3.21 · K 30, and the thin baseline's $2.40 · K 30 · 0.58 V/frame; haiku's diligence variance — the round's original target — is removed at the source, and the old "all-sonnet vision costs $3.61" result (run6) is measured obsolete now that selective registration cut the downstream multiplier — see [`docs/eval/reports/2026-08-21-density-stabilization.md`](docs/eval/reports/2026-08-21-density-stabilization.md) |
| **R11 (density, v0.14.0)** | Attacked the transcript-density variance R10 exposed: calibrated a thin-transcription threshold from 19 preserved run caches (**2.0 V-lines/frame** — every thin run below 1.6, every healthy run above 2.1), wired a deterministic thin-detection check on each vision dispatch's `frames N, V-lines M` reply (M < N×2 → one retry, then fail-soft with an honest low-density note), and extended the lenient contract to label errors: out-of-enum V types normalize via an alias map (`diagram`→`chart`, unknown→`other`) and a stray confidence field in K lines is absorbed, both surfaced as `NORMALIZED n` instead of dropped | Detection scorecard across both gates: **0 false fires, 1 save** (a zoom pass that returned 0 lines was retried into 16), 1 honest miss — a same-model retry cures total failure but not chronic map-pass thinness (9 frames → 9 then 8 V-lines; K 29 vs the 40s of a healthy run), so the knowledge gate was missed and merged by user ruling on variance attribution, with the cure (retry on `sonnet`) queued as the immediate next round — see [`docs/eval/reports/2026-08-21-density-stabilization.md`](docs/eval/reports/2026-08-21-density-stabilization.md) |

<details>
<summary><b>Lessons worth keeping</b></summary>

<br>

**OCR did not meet the quality bar for this domain.** At 1024px, Windows OCR read 4/26 cases and Tesseract with Korean data read 6/26, far below the 95% gate. Direct visual model reading achieved 70/70, so the OCR implementation was rolled back.

**Passing an injected-error gate did not guarantee production performance.** A cheaper audit model caught 3/3 injected errors but produced enough `UNVERIFIABLE` and over-refutation results to require escalation 50% of the time. The selected higher-tier model required 0% escalation in the measured run.

**Sharper frames can encourage models to fill blanks.** Tables now preserve empty or icon-only cells as `(icon only)`, with caption-derived evidence kept outside the table.

**Self-reported coverage cannot count what was never observed.** The pipeline now exposes an `observed` state and assigns unobserved timestamps to 1024px by default.

**Cost comparisons require identical aggregation boundaries.** A partial-vs.-total comparison once suggested an 8.6× increase; remeasurement with the same methodology showed the cost had actually fallen by half.

</details>

---

## Evaluation tooling

### Cost accounting

```bash
python docs/eval/measure-cost.py --marker VIDEO_ID
```

The tool separates orchestrator and subagent cost, deduplicates repeated records by `message.id`, and applies the repository's fixed effective-token weighting. Use `--until` or a dedicated session to avoid counting unrelated work that follows a `/tuto` run.

### Golden-set evaluation

See [`docs/eval/golden-set-protocol.md`](docs/eval/golden-set-protocol.md).

- **R1 Recall**—did the guide miss an action the user needed to perform?
- **Value F1**—are reproducible settings and quoted source values correct?
- Operable values are the primary regression metric; reported values are tracked separately.
- LLM matching must be checked by a user at least once before results are finalized.

---

## Limitations

- Designed primarily for videos **≤30 minutes**; longer videos prompt for a narrower range.
- Conceptual videos are supported, but the output becomes a guide to visible rules, slides, and values rather than a click-by-click procedure.
- `tuto` verifies **screen ↔ claim consistency**. It does **not** prove that the video's advice itself is factually correct.
- Values not visible in evidence frames are intentionally left unresolved instead of inferred.
- Developed and validated on Windows. macOS/Linux are not yet fully validated.
- 산출물은 근거 추적은 되나 표본 감사를 거치지 않는다 — 값은 프레임으로 재확인 가능하다.
- 작은 화면 글자(축약 명령어·설정 키 등)는 비전 서브에이전트가 오독할 수 있다 — 영상당 약 1건
  발생 가능. 교차 대조·`⚠️` 표기·커버리지 감사 3중 안전망이 부분적으로 방어하지만(실측: 11분
  영상에서 교차 대조가 `100`↔`200` 오독 1건을 재확인으로 정정, 32분 영상에서는 flag 9건 중
  1건이 실제 오독으로 판정돼 정정됨 — `108`→`105` KiB/s, 나머지 8건은 정확 확인) 완전히
  막지는 못한다.
- **"조용한 화면"**(타이핑만 있고 화면 변화·언급이 적은 장면 — 예: `.env` 편집)은 공백 표적
  보강의 activity 신호 조준으로도 잡히지 않는다. 그런 장면이 공백 안에 있으면 회수되지
  않으며, 남은 공백은 산출물에 그대로 보고된다(실측:
  [`docs/eval/reports/2026-08-19-gap-backfill.md`](docs/eval/reports/2026-08-19-gap-backfill.md)).
- 전사 밀도가 실행 간 요동한다 — 같은 영상, 같은 프롬프트에서도 확대 전사가 **125줄 ↔
  42줄**로 3배 가까이 차이 난 사례가 실측됐다(선별 등재 게이트, 2026-08-21). 이 요동은
  지식량을 최대 **±30%** 흔들 수 있고, 이 브랜치의 변경과 무관하게 v0.11.0부터 존재해온
  조건이다 — 원인 분리는 됐으나 해결은 아직이라 다음 라운드의 표적으로 남겨둔다(실측:
  [`docs/eval/reports/2026-08-21-selective-reg.md`](docs/eval/reports/2026-08-21-selective-reg.md)).

---

## Cache management

Artifacts are stored in `~/.yta/cache/<video_id>/`. When `CACHE_MAX_VIDEOS` is exceeded, the oldest cached `video.mp4` and `audio.mp3` files are removed while metadata, `evidence.json`, and `video.md` are preserved.

Run cleanup manually with:

```bash
python skills/tuto/scripts/analyze.py --cleanup
```

---

## Contributing

Issues, bug reports, benchmark videos, and pull requests are welcome.

Especially useful contributions include:

- reproducible cases where the screen and captions disagree
- macOS / Linux validation
- tutorials where an important step is missed
- false-positive or over-aggressive audits
- performance or token-cost regression cases

If a tutorial breaks `tuto`, a public video URL and the missed timestamp are especially useful. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Docs

| Document | Purpose |
|---|---|
| [`skills/tuto/SKILL.md`](skills/tuto/SKILL.md) | Orchestrator pipeline contract |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design specs by iteration |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | Implementation plans |
| [`docs/eval/evidence-schema.md`](docs/eval/evidence-schema.md) | **evidence.json schema — canonical spec** |
| [`docs/eval/`](docs/eval/) | Golden-set protocol and cost tooling |

---

## License

[MIT](LICENSE) © 2026 hwangjs

<div align="center">

**If tuto saves you from scrubbing a video frame by frame, consider giving the repo a ⭐.**

<sub>Built as a Claude Code plugin · 352 tests passing</sub>

</div>
