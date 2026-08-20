# 공백 표적 보강 (gap-backfill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 긴 영상의 공백(G) 구간에 있는 화면 전용 치명 정보(실측: 50분 영상에서 Dockerfile 본문·.env 키·명령 인자 3건 영구 유실)를 조건부·정액 예산으로 회수한다. 동시에 실측으로 발견된 **전사 날조**(haiku가 자막 문맥으로 화면 내용을 지어냄 — 2건 확인)를 구조적으로 차단한다.

**Architecture:** 설계 합의는 대화로 완료(감사 실측 2026-08-19: D 5건 중 fable 프레임 원본 대조로 3건 실재·2건 날조 판명). 기반 `master`(v0.9.1)에서 `gap-backfill` 브랜치. 파이프라인 7단계(커버리지)와 8단계(렌더) 사이에 조건부 7.5단계 삽입: `--gap-plan`(코드) → zoom → **blind 전사**(haiku, 자막 미제공) → 보강 합성(sonnet, digest 대조) → `--from-lines`.

**Tech Stack:** evidence.py CLI, 프롬프트 파일, SKILL.md, pytest.

## Global Constraints

- **발동 조건**: 영상 20분 초과 **AND** `--gap-plan` 출력 비어있지 않음 — 짧은 영상 비용·동작 완전 불변.
- **정액 예산**: 공백 프레임 최대 16장(긴 공백 우선), blind 전사 디스패치당 최대 12장(초과 시 분할).
- **blind 전사**: 보강 전사 디스패치에 자막 경로를 절대 주지 않는다 — 날조 재료 차단(실측 근거: CORS 화면에서 main.py 20줄 날조, `CMD ["unicorn"...]` 오타가 지문).
- SKILL.md < 7,000자, transcribe.md < 3,500자, synthesize.md < 3,500자.
- 테스트 append-only(예외 없음 — 이번 라운드는 순수 추가).
- Windows: `python`. 테스트 실행 후 exit를 파이프로 가리지 말 것(`; echo EXIT=$?`).
- 커밋 메시지 끝: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: evidence.py `--gap-plan` — 공백 확대 지점의 결정론적 산출

**Files:**
- Modify: `skills/tuto/scripts/evidence.py` (함수 1개 + CLI 플래그 1개)
- Test: `tests/test_evidence.py` append

**Interfaces:**
- Produces: `gap_zoom_plan(ev: dict, max_frames: int = 16) -> list[str]` — `"MM:SS@1024"` 스펙 리스트. CLI `evidence.py <cache_dir> --gap-plan` → 스펙을 콤마로 이어 한 줄 stdout(공백 없으면 출력 없음, 항상 exit 0). Task 2의 SKILL.md가 이 출력을 그대로 `zoom.py --timestamps`에 넣는다.

- [ ] **Step 1: 실패 테스트 append** (기존 test_evidence.py 픽스처 스타일):

```python
class TestGapZoomPlan:
    def _ev(self, gaps):
        return {"gaps": gaps}
    def test_short_gap_one_midpoint(self):
        # 100초 공백(60~160) → 중점 1개 = 01:50
        specs = gap_zoom_plan(self._ev([{"start": 60.0, "end": 160.0, "reason": "x"}]))
        assert specs == ["01:50@1024"]
    def test_long_gap_two_points(self):
        # 300초 공백(0~300) → 1/3·2/3 = 01:40, 03:20
        specs = gap_zoom_plan(self._ev([{"start": 0.0, "end": 300.0, "reason": "x"}]))
        assert specs == ["01:40@1024", "03:20@1024"]
    def test_cap_prefers_long_gaps(self):
        # 공백 20개(각 70초) → 상한 16으로 잘리되 긴 공백부터
        gaps = [{"start": i*100.0, "end": i*100.0+70+i, "reason": "x"} for i in range(20)]
        specs = gap_zoom_plan(self._ev(gaps), max_frames=16)
        assert len(specs) == 16
    def test_no_gaps_empty(self):
        assert gap_zoom_plan(self._ev([])) == []
    def test_non_dict_gap_skipped(self):
        assert gap_zoom_plan(self._ev(["산문 노트"])) == []
```

- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현** — evidence.py에 (렌더러 함수들 근처):

```python
def gap_zoom_plan(ev: dict, max_frames: int = 16) -> list:
    """G 구간의 확대 지점을 결정론적으로 산출한다 — LLM 비용 0.

    180초 미만 공백은 중점 1개, 이상은 1/3·2/3 지점 2개. 상한 초과 시 긴 공백 우선.
    (실측 2026-08-19: 50분 영상 공백 16구간에 화면 전용 치명 정보 3건 실재)"""
    gaps = [g for g in (ev.get("gaps") or []) if isinstance(g, dict)]
    gaps.sort(key=lambda g: float(g.get("end", 0)) - float(g.get("start", 0)), reverse=True)
    specs = []
    for g in gaps:
        s, e = float(g.get("start", 0)), float(g.get("end", 0))
        pts = [(s + e) / 2] if e - s < 180 else [s + (e - s) / 3, s + 2 * (e - s) / 3]
        for p in pts:
            specs.append(f"{int(p // 60):02d}:{int(p % 60):02d}@1024")
    return specs[:max_frames]
```

CLI: `--gap-plan` 액션 추가 — cache_dir의 evidence.json을 로드해 `",".join(gap_zoom_plan(ev))`를 print(빈 리스트면 아무것도 출력하지 않음), exit 0. evidence.json 부재 시 stderr 한 줄 + exit 0(보강은 선택 단계라 fail-soft).

- [ ] **Step 4: 전체 스위트 PASS** (`python -m pytest tests/ -q; echo EXIT=$?`).
- [ ] **Step 5: Commit** — `feat(evidence): --gap-plan — 공백 확대 지점 결정론 산출 (보강 단계용)`

---

### Task 2: blind 전사 규칙 + SKILL 7.5단계 배선

**Files:**
- Modify: `skills/tuto/prompts/transcribe.md`, `skills/tuto/prompts/synthesize.md`, `skills/tuto/SKILL.md`
- Test: `tests/test_prompt_contract.py`·`tests/test_skill_contract.py` append

**Interfaces:**
- Consumes: Task 1의 `--gap-plan` CLI 출력 형식.

- [ ] **Step 1: 실패 계약 테스트 append**:

```python
# test_prompt_contract.py
class TestBlindTranscribeContract:
    # 실측(2026-08-19): 자막 문맥이 날조의 재료 — CORS 화면에서 main.py 20줄을 지어냄
    def test_blind_mode_no_transcript(self):
        assert "자막 경로가 주어지지 않으면" in TRANSCRIBE
        assert "찾지 마라" in TRANSCRIBE

# test_skill_contract.py — class TestOrchestratorContract에 append
    def test_gap_backfill_stage(self):
        assert "--gap-plan" in TEXT
        assert "20분 초과" in TEXT
        assert "자막" in TEXT and "주지 않는다" in TEXT  # blind 디스패치
```

- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 문구 수정**:
  - **transcribe.md** 규칙 절에 추가: "자막 경로가 주어지지 않으면(보강 모드) 프레임만으로 전사한다 — 자막·다른 파일을 **찾지 마라**. 문맥은 날조의 재료다(실측: 문맥 기반 코드 날조 2건). 프레임에 안 보이면 V라인을 만들지 않는다."
  - **synthesize.md**에 보강 모드 한 단락: "보강 모드(디스패치가 명시): coverage-digest와 gap.lines만 입력 — **digest에 이미 있는 지식은 쓰지 않는다.** V는 gap.lines 전부 복사, K/C는 신규만. 나머지 규칙 동일."
  - **SKILL.md** 7단계와 8단계 사이에 **7.5단계** 삽입 (기존 절 번호는 유지, "7.5"로 표기):
    "**7.5. 공백 표적 보강 (영상 20분 초과 시에만).** `evidence.py "<cache_dir>" --gap-plan` 실행 — 출력이 비면 이 단계를 건너뛴다. 출력이 있으면: ① `zoom.py <id> --timestamps "<출력>"` → `<cache_dir>/gap-frames.txt` && `--add-frames` ② **blind 전사(haiku)**: transcribe.md 보강 모드로 gap-frames.txt 경로만 주고 **자막 경로는 주지 않는다**(날조 차단 — 실측 근거) — 프레임 12장 초과면 두 번에 나눠 디스패치, 출력 `<cache_dir>/gap.lines`(2회면 gap2.lines) ③ 보강 합성(sonnet): synthesize.md 보강 모드로 coverage-digest.txt + gap.lines를 주고 `<cache_dir>/gapfill.lines` 작성 ④ `--from-lines gapfill.lines`(1회, exit 2면 INVALID 1회 재전달) ⑤ 보강 건수를 8단계 `--note "공백 보강 n건"`으로 명시(실패 시 0건 명시)."
  - 콜 수 규율 절의 "본체 12콜"을 "본체 12콜(공백 보강 발동 시 +4콜 허용)"로.
  - 자수 상한 확인: SKILL 7,000자 초과 시 기존 문장을 다듬어 확보하되 계약 문구 보존.
- [ ] **Step 4: 전체 스위트 PASS.**
- [ ] **Step 5: Commit** — `feat(skill): 공백 표적 보강 7.5단계 — blind 전사로 날조 차단, 조건부·정액 예산`

---

### Task 3: 게이트 실측 (컨트롤러 — 서브에이전트 금지)

- [ ] v0.10.0 선범프·배포 → `~/.yta/cache/b0HMimUb4f0` → `-v091`로 개명 보존 → 빈 디렉토리에서 헤드리스 재실행(sonnet·MAX_THINKING_TOKENS=0).
- [ ] 게이트: ① **실재 치명 3건 회수** — 프론트 Dockerfile(FROM nginx:1.27.0·RUN rm -rf·COPY static)·mongo .env 키 2줄·docker exec `/bin/bash`가 evidence에 등재됐는가(v091 산출물엔 없음이 확인된 항목들) ② **날조 0** — 보강으로 추가된 K/V 중 무작위 3건의 근거 프레임을 컨트롤러(fable)가 직접 열어 대조 ③ 비용 ≤ $4.2 (v0.9.1 $3.45 + 예산 $0.75) ④ 짧은 영상 불변(테스트 보장) ⑤ 11분 영상 회귀 재실측 생략(발동 조건 미충족이 테스트로 보장되므로).
- [ ] 결과 보고 — 병합·README는 사용자 판정 후.
