# 분량 비례 예산 + 챕터 렌더러 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 긴 영상(20분+)에서 지식 밀도가 1/3로 깎이는 문제를 해결한다 — 상한을 길이 함수로 바꾸고(A), video.md를 챕터 절로 구성한다(B).

**Architecture:** 설계 합의는 대화로 완료(32:22 실측 tkkbYCajCjM: K 0.9건/분 vs 11분 기준 2.7건/분, G 15구간). 기반 브랜치 `long-video`(master v0.8.1에서 분기). 원칙: **짧은 영상(≤15분)의 기존 동작·비용은 불변** — 11:27 실측치가 회귀 기준선이다.

**Tech Stack:** python(analyze.py·evidence.py), 프롬프트 파일, pytest.

## Global Constraints

- 11:27 영상 기준 수치 불변: 지도 예산 8장, K 상한 30건 — 회귀 금지.
- SKILL.md < 7,000자, 프롬프트 각 < 3,500자.
- 테스트 append-only. 예외(사전 선언): 예산 공식의 기존 수치 단언(캡 16 등)은 새 공식 값으로 갱신하고 커밋 메시지에 테스트명 나열.
- 기존 계약 테스트 `test_knowledge_cap_present`(`"최대 30건" in SYNTHESIZE`)는 깨지 않는다 — 문구에 "최대 30건"을 유지한 채 비례 조항을 덧붙인다.
- Windows: `python`. 테스트: `python -m pytest tests/ -q` (파이프로 exit 가리지 말 것 — `; echo EXIT=$?`).
- 커밋 메시지 끝: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: analyze.py 분량 비례 지도 예산

**Files:**
- Modify: `skills/tuto/scripts/analyze.py:27-28`
- Test: 기존 analyze 예산 테스트 파일(tests/에서 `allocate_map_budget` 검색해 찾는다)

**Interfaces:**
- Produces: `allocate_map_budget`의 캡 16→28. 다른 시그니처 무변경.

- [ ] **Step 1: 실패 테스트** — 기존 예산 테스트 파일에 append (기존 테스트 스타일·헬퍼를 그대로 따른다):

```python
class TestMapBudgetScalesForLongVideos:
    # 실측(2026-08-19, 32:22 영상): 고정 캡 16이 지도 밀도를 0.5장/분으로 깎아 G 15구간 발생
    def test_32min_scales(self):
        # 1942초(32:22) → round(32.37*0.7)=23장 (구 캡 16 초과)
        ...  # 기존 테스트의 호출 방식으로 len(...) == 23 단언
    def test_60min_caps_at_28(self):
        # 3600초 → round(42)=42 → 캡 28
        ...  # len(...) == 28 단언
    def test_11min_unchanged(self):
        # 687초(11:27) → 8장 — 짧은 영상 회귀 금지
        ...  # len(...) == 8 단언
```

- [ ] **Step 2: 실패 확인** (`test_32min_scales`·`test_60min_caps_at_28`만 FAIL, `test_11min_unchanged`는 처음부터 PASS여야 한다 — 아니면 공식 이해가 틀린 것).
- [ ] **Step 3: 구현** — analyze.py 27-28행:

```python
    n = min(28, max(6, round(duration / 60 * 0.7)))
    target = min(28, n + max(0, extra))            # 상한 28은 extra 보강에도 재적용 (분량 비례 라운드)
```

- [ ] **Step 4: 전체 스위트 PASS 확인.** 기존 테스트 중 캡 16을 단언하는 것이 있으면 새 값으로 갱신하고 커밋 메시지에 나열.
- [ ] **Step 5: Commit** — `feat(analyze): 지도 예산 캡 16→28 분량 비례 — 짧은 영상 불변`

---

### Task 2: 렌더러 챕터 절 구성

**Files:**
- Modify: `skills/tuto/scripts/evidence.py` — `render_video_md()`(785행)와 `main()`의 `--render` 처리부
- Test: 기존 렌더러 테스트 파일(tests/에서 `render_video_md` 검색)

**Interfaces:**
- Consumes: `render_video_md(ev, cross_flags=0, coverage_added=0, note="")` 기존 시그니처.
- Produces: `render_video_md(ev, cross_flags=0, coverage_added=0, note="", chapters=None)` — `chapters`는 `[{"start_time": float, "end_time": float, "title": str}, ...]`. CLI `--render`는 `<cache_dir>/info.json`의 `chapters` 키를 읽어 전달한다(파일 없음·키 없음·3개 미만이면 None 취급).

- [ ] **Step 1: 실패 테스트** — 기존 렌더러 테스트 스타일로 append:

```python
class TestRenderChapters:
    CHAPTERS = [
        {"start_time": 0, "end_time": 60, "title": "인트로"},
        {"start_time": 60, "end_time": 120, "title": "설치"},
        {"start_time": 120, "end_time": 180, "title": "실행"},
    ]
    def test_chapter_sections(self):
        # K(ts=70)는 "설치" 절에, K(ts=130)는 "실행" 절에 들어간다
        md = render_video_md(EV_WITH_TWO_ITEMS, chapters=self.CHAPTERS)
        assert "### [01:00] 설치" in md and "### [02:00] 실행" in md
        assert md.index("설치") < md.index("실행")  # 시간순 절 배열
    def test_item_outside_chapters_goes_to_misc(self):
        # ts=999(범위 밖)·ts=None 항목은 "### 기타" 절로
        ...
    def test_no_chapters_keeps_flat_rendering(self):
        # chapters=None이면 기존 유형별 렌더링 그대로 — 기존 테스트가 무변경 PASS인 것도 이 계약의 일부
        md = render_video_md(EV_WITH_TWO_ITEMS)
        assert "## 핵심 지식" in md and "### [" not in md
    def test_chapter_item_carries_type_label(self):
        # 챕터 모드에선 유형 절이 사라지므로 항목 줄에 유형 태그를 단다
        md = render_video_md(EV_WITH_TWO_ITEMS, chapters=self.CHAPTERS)
        assert "- [" in md  # 예: "- [명령] pip install ..."
```

(EV_WITH_TWO_ITEMS는 기존 테스트 픽스처를 재사용하거나 최소 evidence dict를 만들어 쓴다 — knowledge_items 2건에 timestamp 70·130을 준다.)

- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현** — 설계:
  - `chapters`가 유효(리스트, 3개 이상)하면 "## 핵심 지식"의 유형별 절 대신 **"## 챕터별 지식"**: 각 챕터를 시간순으로 돌며 `start_time <= ts < end_time`인 K·C를 모아 절 생성. 빈 챕터는 절을 만들지 않는다. 절 제목 `### [MM:SS] {title}` (`common.fmt_ts` 사용). 항목 줄은 `_item_line` 결과의 `- ` 뒤에 `[{_TYPE_LABELS.get(type, type)}] `를 삽입(주장은 `[주장]`). 범위 밖·timestamp 없는 항목은 마지막 `### 기타` 절.
  - claims를 챕터 절에 흡수하므로 챕터 모드에서는 별도 "## 주장·설명" 절을 만들지 않는다. 누락 후보·검증 스탬프·헤더는 기존 그대로.
  - `main()`의 `--render` 분기: `os.path.join(cache_dir, "info.json")` 존재 시 json 로드, `chapters` 키 전달. json 파손 시 조용히 None이 아니라 stderr에 `NOTE: info.json 파싱 실패 — 평면 렌더링` 한 줄 남기고 진행(fail-loud 완화형 — 렌더링 자체는 완주).
- [ ] **Step 4: 전체 스위트 PASS.**
- [ ] **Step 5: Commit** — `feat(render): 챕터 절 구성 — info.json chapters로 video.md를 시간순 절로`

---

### Task 3: 프롬프트·SKILL 분량 비례 문구

**Files:**
- Modify: `skills/tuto/prompts/transcribe.md` (지도 모드 확대 수), `skills/tuto/prompts/synthesize.md` (K 상한), `skills/tuto/SKILL.md` (3단계 수치)
- Test: `tests/test_prompt_contract.py`·`tests/test_skill_contract.py` append

**Interfaces:**
- Consumes: Task 1의 지도 캡 28 (문구가 코드와 모순되면 안 된다).

- [ ] **Step 1: 먼저 zoom.py를 grep해 1024 장수 상한이 코드로 강제되는지 확인** — 강제라면 상한을 8로 올리는 수정도 이 태스크에 포함하고 테스트를 갱신한다(사전 선언 예외). 문서상 상한뿐이면 코드 무변경.
- [ ] **Step 2: 실패 계약 테스트 append**:

```python
class TestProportionalBudgetContract:
    # 실측(2026-08-19): 고정 상한이 32분 영상 밀도를 1/3로 깎음
    def test_zoom_scales_with_duration(self):
        assert "20분 초과" in TRANSCRIBE   # 지도 모드: 긴 영상은 확대 6~8곳
    def test_knowledge_cap_scales(self):
        assert "최대 30건" in SYNTHESIZE   # 기존 계약 유지
        assert "분당" in SYNTHESIZE        # 비례 조항
```

- [ ] **Step 3: 문구 수정**:
  - transcribe.md 지도 모드 4항: `최대 4곳` → `최대 4곳(영상 20분 초과면 6~8곳)`.
  - synthesize.md 3항: `K는 **최대 30건**` → `K는 **최대 30건**, 단 20분 초과 영상은 분당 2.5건까지(예: 32분 → 80건)`. 자수 <3,500 유지.
  - SKILL.md 3단계: `(1024 최대 4장, 총 6장)` → `(1024 최대 4장·20분 초과 8장, 총 6장·초과 12장)`. 자수 <7,000 유지.
- [ ] **Step 4: 전체 스위트 PASS.**
- [ ] **Step 5: Commit** — `feat(prompts): 확대·지식 상한 분량 비례 — 20분 초과 영상 밀도 회복`

---

### Task 4: 게이트 실측 (컨트롤러 — 서브에이전트 금지)

- [ ] v0.9.0 범프·커밋 → 마켓플레이스·플러그인 갱신 → 캐시 확인.
- [ ] `~/.yta/cache/tkkbYCajCjM` → `-v081`로 개명 보존 후, 빈 디렉토리에서 `export MAX_THINKING_TOKENS=0 && claude -p "/tuto https://www.youtube.com/watch?v=tkkbYCajCjM" --allowedTools "..." --output-format json --model sonnet`.
- [ ] 게이트: ① K ≥ 60건 ② G 구간 수 15 대비 유의미 감소(≤8) ③ video.md에 챕터 절(`### [`) 존재 ④ 비용 ≤ $3.5 ⑤ 날조 0 (v081 산출물과 command·setting 대조) ⑥ 짧은 영상 회귀 없음(테스트로 보장, 재실측 생략).
- [ ] 결과 보고 — 병합·README는 사용자 판정 후.
