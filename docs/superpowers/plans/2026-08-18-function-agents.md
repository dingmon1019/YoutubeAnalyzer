# 함수형 서브에이전트 구조 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 본체를 이미지 0장·긴 출력 0의 얇은 오케스트레이터로 만들고, 판독·합성을 일회용 서브에이전트(haiku/sonnet)의 소멸하는 컨텍스트로 옮겨 `/tuto` 1편을 2회 평균 ≤$1.5로 낮춘다.

**Architecture:** 스펙 `docs/superpowers/specs/2026-08-18-function-agents-design.md`. 기반 브랜치 `function-agents`(= code-render에서 분기 — `--from-lines`·`--render` 재사용). 스크립트(python) 무변경 — 변경은 프롬프트 파일 2개 신설 + SKILL.md 재배선 + 계약 테스트뿐이다.

**Tech Stack:** Claude Code Skill (SKILL.md + prompts/*.md), pytest, 기존 evidence.py CLI.

## Global Constraints

- 외부 API 키를 요구하지 않는다 — 모든 LLM 호출은 Agent 도구(구독 과금)뿐.
- 본체는 분석 파이프라인 중 이미지 파일을 절대 Read하지 않는다.
- `--from-lines`는 patch.lines에 대해 1회 — vision-*.lines를 직접 merge하지 않는다(id_offset 함정).
- SKILL.md < 7,000자 (기존 계약 테스트 상한 유지). 프롬프트 파일 각 < 3,500자.
- 테스트는 append-only. 예외는 Task 2의 `tests/test_skill_contract.py` 1건뿐(문서 재배선으로 무효화되는 단언 — 삭제 목록을 커밋 메시지에 명기).
- Windows: `python` (python3 금지), 커밋 메시지 한국어 + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- 테스트 실행: `cd /d/Repository/YoutubeAnalayzer && python -m pytest tests/ -q`.

---

### Task 1: 프롬프트 파일 2개 + 계약 테스트

**Files:**
- Create: `skills/tuto/prompts/transcribe.md`
- Create: `skills/tuto/prompts/synthesize.md`
- Test: `tests/test_prompt_contract.py` (신규)

**Interfaces:**
- Produces: 두 프롬프트 파일. Task 2의 SKILL.md가 `<SKILL_DIR>/prompts/transcribe.md`·`synthesize.md` 경로로 디스패치한다. 비전 에이전트의 최종 응답 규격 `프레임 N, V라인 M[ | Z: MM:SS@1024,...]`, 합성 에이전트의 최종 응답 규격 `K n건, C n건, V 복사 m건`은 SKILL.md가 그대로 인용한다.

- [ ] **Step 1: 실패하는 계약 테스트 작성** — `tests/test_prompt_contract.py`:

```python
# -*- coding: utf-8 -*-
"""프롬프트 파일 계약 — 함수형 서브에이전트 구조의 지시문은 파일이 정본이다.

본체 SKILL.md가 아니라 이 파일들이 판독·합성 규칙을 나른다. 문구가 사라지면
서브에이전트 행동 계약이 깨지므로 테스트로 고정한다.
"""
from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[1] / "skills" / "tuto" / "prompts"
TRANSCRIBE = (PROMPTS / "transcribe.md").read_text(encoding="utf-8")
SYNTHESIZE = (PROMPTS / "synthesize.md").read_text(encoding="utf-8")


class TestTranscribeContract:
    def test_parallel_read_required(self):
        assert "병렬 Read" in TRANSCRIBE

    def test_verbatim_no_guess(self):
        assert "그대로" in TRANSCRIBE
        assert "추측 금지" in TRANSCRIBE

    def test_uncertain_marker(self):
        assert "⚠️ 화면 확인 필요" in TRANSCRIBE

    def test_zoom_request_format(self):
        # 지도 모드가 확대 요청을 최종 응답으로 돌려주는 것이 본체 무이미지의 전제다
        assert "Z:" in TRANSCRIBE
        assert "1024" in TRANSCRIBE

    def test_recheck_mode_exists(self):
        assert "재확인" in TRANSCRIBE

    def test_one_line_final_response(self):
        assert "최종 응답" in TRANSCRIBE

    def test_v_record_format(self):
        assert "V\t" in TRANSCRIBE or "V<TAB>" in TRANSCRIBE

    def test_length_cap(self):
        assert len(TRANSCRIBE) < 3500


class TestSynthesizeContract:
    def test_no_image_read(self):
        assert "이미지 Read 금지" in SYNTHESIZE

    def test_screen_first_conflict(self):
        assert "conflict=" in SYNTHESIZE
        assert "우선" in SYNTHESIZE

    def test_copies_all_v_lines(self):
        assert "그대로 전부 복사" in SYNTHESIZE

    def test_refs_syntax(self):
        assert "v#" in SYNTHESIZE and "t#" in SYNTHESIZE

    def test_record_kinds(self):
        for kind in ("T\t", "K\t", "C\t", "G\t"):
            assert kind in SYNTHESIZE, kind

    def test_knowledge_types(self):
        assert "command" in SYNTHESIZE and "setting" in SYNTHESIZE

    def test_actionable_no_fabrication(self):
        assert "행동 가능한" in SYNTHESIZE
        assert "근거 없는 지식 금지" in SYNTHESIZE

    def test_no_padding(self):
        # code-render 실측 교훈: 절감분을 추출 부풀림이 소비한다
        assert "쪼개지 마라" in SYNTHESIZE

    def test_length_cap(self):
        assert len(SYNTHESIZE) < 3500
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_prompt_contract.py -q` → FileNotFoundError로 전원 FAIL.

- [ ] **Step 3: `skills/tuto/prompts/transcribe.md` 작성** (아래 전문 그대로):

````markdown
# 비전 전사 에이전트 (transcribe)

너는 프레임 전사기다. 디스패치 프롬프트가 **모드**(지도|확대|재확인), cache_dir,
프레임 목록(경로와 t=시각), 자막 파일 경로, 출력 파일 경로를 준다.

## 규칙 — 전사에는 판단이 없다

- 화면 문자열을 **그대로** 옮긴다(오타·대소문자 포함). 요약·해석·교정 금지.
- 또렷이 읽히지 않으면 값 대신 `⚠️ 화면 확인 필요 (t=MM:SS)` + confidence low. 추측 금지.
- 읽을 텍스트가 없는 프레임(얼굴·전환 화면)은 V라인을 만들지 않는다.
- 값 안의 탭·개행은 스페이스로 치환한다.

## 절차

1. 자막 파일을 Read한다 — 지시어 큐("여기 보세요"·"클릭"·"이 설정"·"입력" /
   "look here"·"click"·"this setting"·"type in") 시점을 파악한다.
2. 프레임 **전량을 한 응답에서 병렬 Read**한다. 순차 Read 금지 — 콜마다 컨텍스트가
   재청구된다.
3. 출력 파일을 **한 번에 Write**한다. 한 줄 = 한 관측 (TAB 구분):

   `V	type	초단위시각	프레임파일명	confidence	화면에서 읽은 문자열 그대로`

   type: slide|ui|chart|code|table|text|other · confidence: high|med|low
4. **모드=지도일 때만** 확대 지점을 고른다:
   ① 값 밀도(터미널·설정창·표·코드) 상위 3~4곳 ② 지시어 큐 시점 우선
   ③ 지도가 60초 이상 비는 구간 1곳 — 못 본 화면은 "텍스트 없음"으로 확정할 수 없다.
   최종 응답 끝에 `Z: MM:SS@1024,MM:SS@1024,...` (전부 1024, 최대 4곳).
5. **모드=재확인일 때** 지정된 프레임만 Read해 문제의 값을 다시 판독하고, 정정
   V라인을 출력 파일에 Write한다.

## 최종 응답은 한 줄이다

`프레임 N, V라인 M` (지도 모드는 ` | Z: ...`를 덧붙인다). 전사 내용을 응답에
반복하지 마라 — 본체는 네 파일을 열어보지 않는다.
````

- [ ] **Step 4: `skills/tuto/prompts/synthesize.md` 작성** (아래 전문 그대로):

````markdown
# 지식 합성 에이전트 (synthesize)

너는 자막과 화면 전사에서 근거 추적되는 지식을 추출한다. 디스패치 프롬프트가
cache_dir, 입력 파일들(pass1-report.txt 자막, vision-*.lines 전사), 출력 파일
(patch.lines)을 준다.

**이미지 Read 금지.** 근거는 자막과 전사 텍스트뿐이다. 전사에 없는 화면 값을
만들어내지 마라.

## 절차

1. 입력 파일 전부를 한 응답에서 병렬 Read한다.
2. patch.lines를 **한 번에 Write**한다 (TAB 구분, 첫 필드 = 레코드 종류):

```
T	tutorial	high	근거 한 줄
V	ui	132.0	t0212_1024.jpg	high	화면에서 읽은 문자열 그대로
K	command	88.0	v1;t12	pip install -U yt-dlp
C	132.0	v1;t12	주장 한 문장	conflict=16배=>16.3x
G	350.0	469.0	지도 공백
```

- 첫 줄 T: 영상유형·확신도·근거 한 줄.
- **V: vision-*.lines의 V라인을 그대로 전부 복사한다** (vision-map → vision-zoom 순).
  id는 등장 순서대로 v1..vN 자동 부여 — 네가 id를 쓰지 않는다. `⚠️` 라인도
  복사한다(확인이 필요하다는 사실 자체가 기록이다).
- K(지식): type은 concept·procedure·action·command·setting·prerequisite·result·
  criterion·warning·example·comparison. content는 행동 가능한 수준으로
  ("Add Python to PATH를 체크한다"). refs는 `;` 구분 — `v#`(위 V 순번)·`t#`(자막
  인덱스, 0부터). **영상에 있는 것만 — 근거 없는 지식 금지.**
- C(주장): 핵심 주장 + refs. **자막값 ≠ 전사값이면 전사(화면)를 우선**하고 5번째
  필드에 `conflict=자막값=>화면값`.
- G: 프레임이 60초 이상 비는 구간(초 단위 시작·끝). 산문 노트 금지.
- 값 안의 탭·개행은 스페이스로 치환한다.

3. 지식은 빠짐없이, 그러나 부풀리지 않는다 — 같은 사실의 재표현을 여러 K로
   **쪼개지 마라**.
4. merge 게이트는 본체가 돌린다. INVALID 재요청이 오면 지적된 줄만 고쳐 파일
   전체를 다시 Write한다.

## 최종 응답은 한 줄이다

`K n건, C n건, V 복사 m건`. 내용을 응답에 반복하지 마라.
````

- [ ] **Step 5: 통과 확인** — `python -m pytest tests/test_prompt_contract.py -q` → 전원 PASS. 전체 스위트도 실행해 기존 테스트 무영향 확인: `python -m pytest tests/ -q`.

- [ ] **Step 6: Commit**

```bash
git add skills/tuto/prompts/ tests/test_prompt_contract.py
git commit -m "feat(prompts): 비전 전사·지식 합성 프롬프트 파일 — 지시문을 본체 상주 컨텍스트 밖으로"
```

---

### Task 2: SKILL.md 오케스트레이터 재배선 + 계약 테스트 갱신

**Files:**
- Modify: `skills/tuto/SKILL.md` (전면 교체 — 아래 전문)
- Modify: `tests/test_skill_contract.py` (append-only 예외 — 사전 선언됨)

**Interfaces:**
- Consumes: Task 1의 `prompts/transcribe.md`·`synthesize.md` 경로와 최종 응답 규격.
- Produces: 오케스트레이터 SKILL.md. 게이트 실측(Task 3)이 이 문서로 헤드리스 실행된다.

- [ ] **Step 1: 현재 계약 테스트 파악** — `tests/test_skill_contract.py`를 Read해 단언 목록을 뽑는다. 유지·이동·삭제를 다음 정책으로 분류한다:
  - **유지**: 문서 길이 상한(<7000), frontmatter, 6개 차별점(diff1-6), 단일 인터페이스, 후속 질문 캐시 우선, bare merge 금지, 실패 평문 보고.
  - **이동**: 화면 우선·conflict·`⚠️`·TSV 레코드·행동 가능 content 등 판독/합성 규칙 단언 → 이미 Task 1의 `test_prompt_contract.py`가 커버 — SKILL.md 대상 단언은 삭제하고 커밋 메시지에 "이동: <테스트명> → test_prompt_contract.py" 명기.
  - **삭제**: 본체가 프레임을 병렬 Read한다는 단언, 본체의 patch.lines Write 단언 등 solo 전용 행동 — 새 구조에서 사실이 아니게 된 것. 커밋 메시지에 사유와 함께 나열.

- [ ] **Step 2: 새 계약 테스트 추가** (같은 파일에 append — 오케스트레이터 계약):

```python
class TestOrchestratorContract:
    def test_main_never_reads_images(self):
        assert "이미지" in TEXT and "Read하지 않는다" in TEXT

    def test_dispatches_prompt_files(self):
        assert "prompts/transcribe.md" in TEXT
        assert "prompts/synthesize.md" in TEXT

    def test_vision_returns_zoom_request(self):
        # 본체가 이미지 없이 확대를 결정하는 유일한 통로
        assert "Z:" in TEXT

    def test_single_from_lines_batch(self):
        # vision-*.lines 직접 merge 금지 — id_offset 함정
        assert "vision" in TEXT and "patch.lines" in TEXT

    def test_haiku_vision_sonnet_synthesis(self):
        assert '"haiku"' in TEXT and '"sonnet"' in TEXT

    def test_call_budget_present(self):
        assert "12콜" in TEXT

    def test_no_echo_of_artifacts(self):
        assert "echo" in TEXT or "열어보지" in TEXT
```

  (`TEXT`는 기존 파일의 SKILL.md 로드 변수를 그대로 쓴다.)

- [ ] **Step 3: 실패 확인** — `python -m pytest tests/test_skill_contract.py -q` → 신규 단언 FAIL(기존 문서), Step 1 분류로 삭제 예정 단언은 아직 PASS.

- [ ] **Step 4: SKILL.md 전면 교체** (아래 전문 그대로 — frontmatter의 description은 기존 것을 한 글자도 바꾸지 않고 유지한다):

````markdown
---
name: tuto
description: <기존 description 그대로 복사 — 변경 금지>
argument-hint: "<video-url> [자연어 요청]"
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent
user-invocable: true
---

# /tuto — 유튜브 영상 → 근거 추적되는 작업 지식 (오케스트레이터)

`/tuto <video-url> [자연어 요청]` — 인터페이스는 이것 하나다.

**산출물 2개.** `evidence.json`(기계 정본 — 모든 지식이 프레임·타임스탬프·자막 인덱스로
근거 추적된다) + `video.md`(사람용 문서). 자막 요약이 아니라 **화면을 판독**한다: 자막이
"16배"라 말해도 화면이 `16.3x`면 화면 값을 채택하고 불일치를 `conflict`로 보존한다.
이것이 /watch와의 차이다 — watch는 세션이 끝나면 아무것도 남지 않는다.

**사용자 요청이 함께 왔으면 분석에서 멈추지 않는다.** 분석 완료 후 곧바로 그 요청을
이어서 수행한다(설명·비교·적용·실행). 사용자가 "이제 해줘"라고 다시 말하게 하지 않는다.

**너는 오케스트레이터다 — 분석 파이프라인 중 이미지를 절대 Read하지 않는다.** 판독·합성은
일회용 서브에이전트가 자기 컨텍스트에서 수행하고 파일로 남긴다. 이미지·긴 산출물이 본체에
상주하면 콜마다 재청구된다(실측: 본체 단독 $2.91 → 이 구조 목표 $1.2). 너는 vision-*.lines·
patch.lines·video.md 내용을 열어보지도, 응답에 echo하지도 않는다.

**SKILL_DIR**: 이 문서가 있는 디렉토리. **PROMPTS** = `<SKILL_DIR>/prompts`. 명령은
`python "<SKILL_DIR>/scripts/<이름>.py"` (Windows — `python3` 금지).

## 파이프라인

**0. 프리플라이트 (세션 첫 호출만).** `setup.py --check`. exit 0이면 진행하되 stderr
NOTE(yt-dlp 최신성·JS 런타임 부재)는 사용자에게 한 줄 알린다. exit 2면 설치 안내.

**1. 패스1.** `analyze.py "<url>"` (Bash timeout 600000) — 출력을
`<cache_dir>/pass1-report.txt`로 리다이렉트. STATUS·`== CACHE ==`·`== FRAMES ==` 줄만
확인한다(경로·목록 파악용 — 프레임 파일은 열지 않는다). 자막 없음이면 사용자에게 알리고
프레임 중심 진행, 30분 초과 WARNING이면 구간 지정을 제안한다.

**2. 비전① (Agent, `model: "haiku"`).** 디스패치 프롬프트는 경로만 나른다:
"`<PROMPTS>/transcribe.md`를 Read하고 그대로 수행. 모드=지도. 프레임: <FRAMES 목록>.
자막: <cache_dir>/pass1-report.txt. 출력: <cache_dir>/vision-map.lines".
에이전트의 최종 응답 `프레임 N, V라인 M | Z: MM:SS@1024,...`에서 Z 목록을 얻는다 —
이것이 확대 판정이다. 네가 프레임을 보고 고르지 않는다.

**3. 확대.** `zoom.py <id> --timestamps "<Z목록>"` (1024 최대 4장, 총 6장) 출력을
`<cache_dir>/zoom-out.txt`로 저장하고 `evidence.py "<cache_dir>" --add-frames ...`까지
`&&` 한 호출로. 새 프레임도 너는 Read하지 않는다.

**4. 비전② (haiku).** 같은 프롬프트 파일, 모드=확대, 프레임=zoom-out.txt의 경로들,
출력=`<cache_dir>/vision-zoom.lines`.

**5. 합성 (Agent, `model: "sonnet"`).** "`<PROMPTS>/synthesize.md`를 Read하고 수행.
입력: pass1-report.txt, vision-map.lines, vision-zoom.lines. 출력:
<cache_dir>/patch.lines". V 전부 복사 + K/C/G — 단일 배치가 계약이다.

**6. 병합 + 교차 대조.**
`evidence.py "<cache_dir>" --from-lines "<cache_dir>/patch.lines" --cross-check` 한 호출.
exit 2면 stderr의 INVALID 줄을 합성 에이전트에 그대로 재전달해 1회 수정시킨다(파일 수정도
에이전트가 한다). CROSSCHECK flag가 나오면 **비전 재확인(haiku)**: transcribe.md 재확인
모드로 해당 프레임·값 후보만 주고 `<cache_dir>/recheck.lines`에 정정 V라인을 받아
`--from-lines`로 반영한다. flag 수를 기억한다 — 8단계 `--cross-flags`에 넣는다(정정
반영 여부와 무관하게 발견 건수를 기록한다).

**7. 커버리지 감사 (haiku).**
`evidence.py "<cache_dir>" --coverage-input > "<cache_dir>/coverage-digest.txt"` 후
디스패치: "이미지 Read 금지. <digest 경로>와 <pass1-report.txt 경로>를 Read하고, 이
영상을 안 본 에이전트가 작업하려면 알아야 하는데 digest에 없는 지식을 자막으로 검증해
**명백한 것만** `K	type	초단위시각	t#refs	content` 형식으로
`<cache_dir>/coverage.lines`에 Write. 없으면 파일을 만들지 마라. 최종 응답: '보강 n건'".
n>0이면 `--from-lines coverage.lines`로 반영한다(1회 한정). n을 기억한다 —
`--coverage-added`에 넣는다. 자막 없는 영상은 이 단계를 생략하고 8단계에서
`--note "커버리지 감사 생략 — 자막 없음"`.

**8. video.md — 코드가 생성한다.**
`evidence.py "<cache_dir>" --render --cross-flags <6단계 flag 수> --coverage-added <7단계 n>`
문서는 evidence.json의 결정론적 렌더링이며 "표본 감사 미실시" 명시를 포함한다. 네가
문서를 쓰거나 고치지 마라 — 고칠 것이 있으면 evidence를 고치고 다시 render한다.

**9. 응답.** 요약(영상유형·핵심 지식 수·⚠️ 건수 — 에이전트 최종 응답의 집계만 쓴다) +
두 산출물 경로. 자연어 요청이 있었으면 **곧바로 이어서 수행한다.**

## 콜 수 규율 — 비용의 지배 요인

`cache_read`는 콜마다 이전 컨텍스트 전체를 재청구한다. 서브에이전트는 순차 의존이다
(비전①→확대→비전②→합성) — 각 Agent 결과를 기다려 다음을 디스패치한다. 독립 셸 명령은
`&&` 연쇄, 같은 스크립트 플래그는 한 호출에 결합. **`--coverage-input`과 `--render`는
절대 한 호출에 묶지 마라** — 사이에 감사·보강이 있고, 같은 호출에서는 `--render`가 먼저
실행된다. 본체 **12콜 이내**를 목표로 하되, 초과해도 남은 단계를 생략하지 말고 완주한다 —
콜 절약보다 산출물 완결이 우선이다.

## 후속 질문

이미 분석된 영상은 `<cache_dir>/evidence.json`으로 먼저 답한다(질의 응답 단계에서는
evidence.json Read 허용 — 이것이 캐시 재질의다). **analyze.py 재실행 금지.** 근거가
부족할 때만 `zoom.py --timestamps`로 프레임을 만들고 비전 재확인 에이전트로 판독시켜
`--from-lines`로 반영한다 — 이때도 이미지는 에이전트가 본다. `video.mp4 evicted` 오류면
재분석이 필요함을 알린다.

## 실행형 요청 시

영상 명령을 맹목 실행하지 않는다: 환경 점검 → 호환성 확인 → 적용 → 검증.
`evidence.json`의 `prerequisite`·`setting`·`command`를 현재 환경과 대조한 뒤 적용한다.
위험 명령(`curl | bash`·삭제·`sudo`)은 세션의 안전 정책을 따른다.

## 실패 시

다운로드 실패는 평문으로 있는 그대로 보고하고 재시도 루프를 돌지 않는다(1회 자동 폴백은
스크립트가 한다). 서브에이전트가 출력 파일을 만들지 못하면 같은 디스패치를 **1회만**
재시도하고, 그래도 실패면 그 단계 없이 완주하며 사용자에게 명시한다. 모든 flags·WARNING은
보고에 그대로 반영한다.
````

- [ ] **Step 5: 통과 확인** — `python -m pytest tests/ -q` 전체 스위트 PASS. SKILL.md 자수 확인(`len < 7000`) — 계약 테스트가 잡는다.

- [ ] **Step 6: Commit** — 삭제·이동한 테스트를 메시지에 나열:

```bash
git add skills/tuto/SKILL.md tests/test_skill_contract.py
git commit -m "feat(skill): 오케스트레이터 재배선 — 본체 무이미지, 판독·합성은 일회용 서브에이전트로"
```

---

### Task 3: 게이트 실측 ×2 + 전사 A/B (컨트롤러 — 서브에이전트 금지)

**Files:**
- Modify: `.claude-plugin/marketplace.json`·`skills/tuto/plugin.json` 등 버전 표기 (0.7.0 선범프)
- Create: `docs/eval/reports/2026-08-18-function-agents.md` (실측 보고서)

- [ ] **Step 1:** v0.7.0 선범프 커밋 → `claude plugin marketplace update yta && claude plugin update tuto@yta` → 플러그인 캐시의 SKILL.md에 "오케스트레이터" 포함 확인.
- [ ] **Step 2:** `~/.yta/cache/7MEsgHKQGLg`를 `7MEsgHKQGLg-code-render`로 개명 보존(solo-opus 보존본은 그대로).
- [ ] **Step 3:** 실측 1회차 — 빈 디렉토리에서 `claude -p "/tuto https://www.youtube.com/watch?v=7MEsgHKQGLg" --allowedTools "Bash Read Write Edit Glob Grep Skill Agent Task TodoWrite" --output-format json --model opus`. 종료 후 `measure-cost.py --marker 7MEsgHKQGLg --session <id>`. 캐시를 `-fa-run1`로 개명.
- [ ] **Step 4:** 실측 2회차 동일 → `-fa-run2`.
- [ ] **Step 5:** 판정 — 스펙 §4: 평균 ≤$1.5(개별 ≤$1.8), $/지식항목 ≤$0.05, 지식 ≥28건, ≤15분, command·setting 오독 0(전사 A/B: run 산출물의 command·setting 값을 solo-opus 보존본과 수동 대조, `compare-evidence.py`는 참고 지표). haiku 전사 오독 시 폴백: SKILL.md 2·4단계만 `model: "sonnet"`으로 바꿔 1회 재측정.
- [ ] **Step 6:** 보고서 작성·커밋, 사용자에게 판정 보고.

### Task 4: 문서·병합 (게이트 통과 시 — 컨트롤러)

- [ ] README 수치·버전 문단 갱신, 스펙 §6 실측치 기입, 사용자 승인 후 master 병합·배포. 실패 시: 스펙 §4-6 롤백(SKILL.md·prompts만 되돌림) 후 결과 보고.
