<div align="center">

# 🎬 tuto

### Turn YouTube tutorials into verified, reproducible instructions for Claude Code.

**Not another AI video summarizer.** `tuto` reads the actual screen—settings, buttons, values, and operation order—then asks independent audit agents to challenge the result before it reaches you.

**유튜브를 요약하는 게 아니라, 실제로 따라 할 수 있게 만듭니다.**

자막만 믿지 않고 화면의 설정값·버튼명·조작 순서를 직접 읽고 독립 감사 에이전트가 검증합니다.

[![Version](https://img.shields.io/badge/version-0.1.6-blue.svg)](https://github.com/dingmon1019/YoutubeAnalyzer/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-101%20passed-brightgreen.svg)](tests/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2.svg)](https://claude.com/claude-code)
[![Languages](https://img.shields.io/badge/video-KO%20%7C%20EN-orange.svg)](#)

```text
/tuto https://youtu.be/VIDEO_ID
```

**YouTube → screen evidence → verified steps → `guide.md`**

</div>

---

## Why tuto?

Tutorial captions are often incomplete or wrong exactly where precision matters most.

| Caption / ASR said | Screen actually showed |
|---|---|
| `python` | **`python3`**—confirmed by a user following the tutorial |
| slowdown **98x** | **`0.98x`**—the Korean ASR dropped the decimal point |
| **16x** difference | **`16.3x`**—90,991 vs. 5,584 |
| **600** followers | **`576`** |
| `irresistible` | **`irresistable`**—the original on-screen typo is preserved |

`tuto` treats the **screen as evidence**. When captions and frames disagree, the frame wins and the conflict is noted. If a value cannot be read safely, tuto says `⚠️ needs visual check` (`⚠️ 화면 확인 필요` in Korean output) instead of guessing.

> The goal is not to sound confident. The goal is to make the tutorial reproducible.

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

Or ask for only the part you need:

```text
/tuto https://youtu.be/VIDEO_ID show me only the Python PATH setup
```

Output:

```text
~/.yta/cache/<video_id>/guide.md
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

A guide is written as actionable steps with timestamped visual evidence.

```markdown
## Step 4: Run installer—Add Python to PATH + Install Now (02:56–04:05)

1. Open the installer → "Install Python 3.9.6 (64-bit)".
   Default path: `...\AppData\Local\Programs\Python\Python39` (t=03:23)
2. "Install launcher for all users (recommended)" is checked.
   "Add Python 3.9 to PATH" is unchecked at this frame. (t=03:23)
3. ⚠️ The exact checkbox and click moments are hidden by a transition. (t=03:51)

## Audit stamp
Sample audit: 5/6 claims matched, 1 corrected; 1 claim escalated for re-checking.
Coverage audit: 2 missing steps recovered.
```

Follow-up questions in the same session reuse cached frames and captions, so the video does not need to be downloaded again.

---

## Measured results

These are measured golden-set and regression-run results, not marketing estimates. The evaluation protocol uses 3–5 user-verified tutorials and is intended for per-video regression diagnosis, not statistical generalization.

| Metric | Result | Meaning |
|---|:---:|---|
| **Hallucinated values** | **0** | Precision **1.000** on the golden set |
| **Step recall (R1)** | **0.913** | 21 / 23 expected steps recovered |
| **Value F1** | **0.909** | Settings, labels, and numeric values |
| **Orchestrator image cost** | **−95%** | `cache_write` 432,788 → 21,594 |
| **Total pipeline cost** | **−27%** | 3.35M → 2.44M tokens on a 19-minute video |
| **Download + analysis** | **8.1× faster** | 154s → 19s |
| **Zoom extraction** | **5.4× faster** | 327s → 61s |
| **Audit escalation** | **0%** | On the selected audit model |
| **Tests** | **101 passing** | Current regression suite |

See [`docs/eval/`](docs/eval/) for the evaluation protocol and cost-accounting tool.

---

## How it works

```text
MAP                    ZOOM                   BUILD                 VERIFY
────────────────       ─────────────────      ─────────────────     ─────────────────
analyze.py              reading agents         guide builder         sample audits ×6
├─ yt-dlp               → zoom-plan.json       ├─ frame reading      ├─ independent context
├─ native captions      ├─ caption cues        ├─ crop + re-read     ├─ "try to refute"
├─ heatmap / chapters   ├─ chapter bounds      └─ guide.md           ├─ escalate conflicts
├─ activity peaks       ├─ activity coverage                         └─ coverage audit
└─ map frames           └─ gap detection
```

### 1. Signal-weighted frame selection

Uniform sampling and scene-change detection can skip static screens—exactly where tutorials often show settings, terminal commands, tables, and configuration values.

`tuto` combines YouTube heatmaps, chapter boundaries, activity peaks, caption cue words such as “click” / “look here,” and frame-gap detection.

### 2. Resolution tiering

Text-heavy frames such as slides, tables, menus, and terminals are extracted at **1024px**; illustrations, transitions, and talking heads use **512px**. Frames not observed during the map pass default to 1024px rather than being assumed irrelevant. The zoom budget is capped at 20 high-resolution frames and 60 total frames per session. Unclear regions are re-read with `zoom.py --crop`, capped at five crops per video.

### 3. Gap detection

Low-motion verification sections near the end of tutorials are easy for samplers to miss. `tuto` explicitly revisits gaps of **60 seconds or more**. This rule was added after two measured runs omitted entire conclusion sections.

### 4. Independent adversarial audit

A fresh agent receives a single claim and its evidence frame—**not the whole guide**—and is asked to refute the claim. Disagreements can be escalated for re-checking.

This reduces confirmation bias from having the same model both write and approve its own answer.

### 5. Coverage audit

A checklist of expected steps is built from captions and chapters before the final guide is compared against it. This catches omissions that claim-by-claim auditing cannot see.

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
| **R4** | Removed images from the orchestrator context | `cache_write` **−95%**, total cost **−27%**, with a net quality improvement |

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

Artifacts are stored in `~/.yta/cache/<video_id>/`. When `CACHE_MAX_VIDEOS` is exceeded, the oldest cached `video.mp4` and `audio.mp3` files are removed while metadata and guides are preserved.

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
| [`docs/eval/`](docs/eval/) | Golden-set protocol and cost tooling |

---

## License

[MIT](LICENSE) © 2026 hwangjs

<div align="center">

**If tuto saves you from replaying a tutorial frame by frame, consider giving the repo a ⭐.**

<sub>Built as a Claude Code plugin · 101 tests passing</sub>

</div>
