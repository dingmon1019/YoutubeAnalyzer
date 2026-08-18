<div align="center">

# 🎬 tuto

### Let AI watch YouTube for you.

Turn YouTube videos into **verified working knowledge** for AI agents — transcripts, screen text, slides, UI, charts, numbers, actions, and timestamps.

**유튜브 영상을 직접 보지 않아도 됩니다.**

AI가 대신 영상을 보고, 자막과 화면을 함께 이해하고, 검증된 지식으로 변환합니다.
이후 AI는 그 내용을 설명하거나 질문에 답하고, 현재 작업과 비교하거나 튜토리얼을 따라 할 수 있습니다.

[![Version](https://img.shields.io/badge/version-0.4.0-blue.svg)](https://github.com/dingmon1019/YoutubeAnalyzer/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-266%20passed-brightgreen.svg)](tests/)
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
  "verification": { "status": "verified", "auditor": "sonnet" }
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

Confidence is **never a fabricated number** — the pipeline has no basis for probability estimates, so only `high|medium|low` and `verified|disputed|unverifiable|unaudited` are allowed. `unaudited` is deliberately distinct from `verified`: sample audits cover 6 claims, so most claims are simply not audited, and that must not look like passing.

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

`video.md`의 구조는 영상에 따라 달라집니다. 튜토리얼이면 절차 중심, 강의면 개념 중심으로 조직됩니다. 아래는 튜토리얼 예시입니다.

```markdown
## Step 4: Run installer—Add Python to PATH + Install Now (02:56–04:05)

1. Open the installer → "Install Python 3.9.6 (64-bit)".
   Default path: `...\AppData\Local\Programs\Python\Python39` (t=03:23)
2. "Install launcher for all users (recommended)" is checked.
   "Add Python 3.9 to PATH" is unchecked at this frame. (t=03:23)
3. ⚠️ The exact checkbox and click moments are hidden by a transition. (t=03:51)

## Audit stamp
Sample audit: 5/6 claims matched, 1 corrected; 1 claim escalated for re-checking.
Coverage audit: 2 missing knowledge items recovered.
```

Follow-up questions in the same session reuse cached frames and captions, so the video does not need to be downloaded again.

---

## Measured results

These are measured golden-set and regression-run results, not marketing estimates. The evaluation protocol uses 3–5 user-verified tutorials and is intended for per-video regression diagnosis, not statistical generalization.

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
| **Tests** | **266 passing** | Current regression suite |

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

See [`docs/eval/`](docs/eval/) for the evaluation protocol and cost-accounting tool.

---

## How it works

```text
MAP              ZOOM             EVIDENCE          VERIFY            ORGANIZE
──────────       ──────────       ──────────        ──────────        ──────────
analyze.py       reading agent    builder           sample audits ×6  builder
├ yt-dlp         → zoom-plan      ├ frame reading   ├ independent ctx ├ 9 coverage
├ captions       ├ caption cues   ├ crop + re-read  ├ "try to refute"   questions
├ heatmap        ├ chapter bounds ├ visual_evidence ├ escalate        ├ outline chosen
├ chapters       ├ activity cover ├ claims          └ coverage audit    per video
├ activity peaks ├ gap detection  └ knowledge_items        ↓          └ video.md
└ map frames     └ visual-coverage.json      ↓            --verdicts
                                   evidence.json ←─────────┘
```

`evidence.json`이 정본이고 `video.md`는 그것을 사람이 읽게 조직한 것입니다.
**문서를 먼저 쓰고 근거를 맞추지 않습니다** — 순서가 바뀌면 문서에 맞춰 근거를 지어내게 됩니다.

### 1. Signal-weighted frame selection

Uniform sampling and scene-change detection can skip static screens—exactly where tutorials often show settings, terminal commands, tables, and configuration values.

`tuto` combines YouTube heatmaps, chapter boundaries, activity peaks, caption cue words such as “click” / “look here,” and frame-gap detection.

### 2. Resolution tiering

Text-heavy frames such as slides, tables, menus, and terminals are extracted at **1024px**; illustrations, transitions, and talking heads use **512px**. Frames not observed during the map pass default to 1024px rather than being assumed irrelevant. The zoom budget is capped at 20 high-resolution frames and 60 total frames per session. Unclear regions are re-read with `zoom.py --crop`, capped at five crops per video.

### 3. Gap detection

Low-motion verification sections near the end of tutorials are easy for samplers to miss. `tuto` explicitly revisits gaps of **60 seconds or more**. This rule was added after two measured runs omitted entire conclusion sections.

### 4. Independent adversarial audit

High-value claims **and actionable knowledge items** are independently challenged against their source evidence. A fresh agent receives a single item and its evidence—**not the rendered document**—and is asked to refute it. Disagreements can be escalated for re-checking.

Sampling is ordered by how much an item can affect an agent's actions: `command` · `setting` · `action` · `criterion` · `prerequisite` · `warning` · … · `concept`. A misread `command` is more dangerous in practice than a misread claim.

This reduces confirmation bias from having the same model both write and approve its own answer.

### 5. Coverage audit

Coverage audit builds an **expected knowledge checklist** from the source and compares it against **`claims` and `knowledge_items` in `evidence.json`** — not against document headings.

An adaptive `video.md` heading like `## Phase 1` says nothing about what it contains, and `evidence.json` is the canonical source anyway. So completeness is checked as `source → evidence` first, and `evidence → video.md` second.

**The source includes independent visual observations.** Values that appear only on screen and are never spoken are this project's whole point — but if the builder misses one, a captions-only coverage check cannot even know it existed. So the reading agent, which is **already looking at the map frames**, also records lightweight existence signals (`visual-coverage.json`): *"a terminal command is visible here"*, *"installer options are visible here"*.

This costs **no additional image reads** and keeps the roles separate — the reading agent observes, the builder extracts, the coverage agent compares. Observations are existence signals, never the source of truth for a value.

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
| [`skills/tuto/SKILL.md`](skills/tuto/SKILL.md) | Pipeline and orchestration contract |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design specs by iteration |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | Implementation plans |
| [`docs/eval/evidence-schema.md`](docs/eval/evidence-schema.md) | **evidence.json schema — canonical spec** |
| [`docs/eval/`](docs/eval/) | Golden-set protocol and cost tooling |

---

## License

[MIT](LICENSE) © 2026 hwangjs

<div align="center">

**If tuto saves you from scrubbing a video frame by frame, consider giving the repo a ⭐.**

<sub>Built as a Claude Code plugin · 266 tests passing</sub>

</div>
