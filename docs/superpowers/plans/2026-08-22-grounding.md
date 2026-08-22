# 화면 근거 보장 (grounding) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** 화면을 **읽고도 지식으로 만들지 않는** 구멍을 막는다. v0.18.0 실측에서 지식 60건 중
frame 인용 0건, 그 결과 자막값이 화면값을 이겨 **문서에 틀린 설정값이 실렸다.**

## 실패 사례 (이 라운드의 회귀 시험이자 존재 이유)
`pwGeWRlrU10` 03:33~03:37 Submagic 캡션 설정:

| 출처 | 값 |
|---|---|
| 자막 t123 | "scale it down to **30**" |
| 화면 확대 프레임(217s) | `Size` → **25** |
| v0.18.0 정본에 실린 것 | "Scale caption size down to **30**" (근거: transcript t27) |

계약상 **화면 우선 + `conflict=30=>25`** 여야 했다. 실패한 이유 3겹:
1. **계량 게이밍** — 하한 32건이 생기자 합성이 값싼 재료(자막)로 채웠다. V 10건을 등재해 놓고
   한 건도 인용하지 않았다(선별 등재 계약 위반이기도 하다 — 인용하지 않을 V는 복사 대상이 아니다).
2. **감사 경로의 구멍** — 이 항목은 커버리지 감사(설계상 텍스트 전용, 화면 접근 없음)가 낸
   것이고, 화면과 대조되는 관문 없이 정본에 직행했다.
3. **교차 대조의 사각** — `cross_check_values`는 `visual_evidence` **내부만** 순회한다. 화면 25와
   지식 30을 마주 놓는 코드가 없다. (덤: `_near_miss`는 편집거리 1이라 25↔30은 원래 못 잡는다.)

또한 화면에만 있던 `Stroke: None`·`Display mode: 5 words`·보조 폰트·위치 슬라이더는 지식에
**아예 없다** — 따라하려면 필요한 값들이 자막이 말하지 않았다는 이유로 통째로 빠졌다.

## Global Constraints
SKILL <7,000자 · synthesize <2,600자, 전체 스위트 PASS, Windows python,
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

---

### Task A: 결정론 화면 검문 (evidence.py) — 병렬 가능
**Files:** skills/tuto/scripts/evidence.py, tests/test_evidence.py(append)

1. **화면↔지식 값 검문 `screen_check(ev)`**: `knowledge_items`·`claims` 중 **type이 `setting`
   또는 `command`인 항목**(설정·명령은 화면이 정본이다 — 범위를 좁혀 오탐을 막는다)을 훑어,
   본문의 숫자 토큰이 **±90초 창의 `visual_evidence` 값들 어디에도 없고**, 그 창에 숫자를 가진
   V가 하나 이상 있으면 flag: `{"item_id", "text_value", "screen_candidates":[...], "v_ids":[...]}`.
   편집거리를 쓰지 마라(25↔30은 거리 2다). 창에 V가 없으면 flag하지 않는다(미관측 ≠ 모순).
2. **정본 표기**: flag된 항목에 `"screen_conflict": {"text": "30", "screen": ["25"], "v_ids": ["v7"]}`를
   달아 둔다. **본문 문자열을 자동 치환하지 마라** — 조용한 변조 금지, 사람이 보게 만드는 게 목적이다.
3. **렌더 노출**: `render_video_md`가 해당 항목 줄 끝에 `⚠️ 화면값 25 (자막 30)`를 붙인다.
4. **모든 병합에서 작동**: `--from-lines` 병합 시(합성분·보강분·**커버리지 감사분 포함**) 검문을
   돌리고, stdout에 `SCREENCHECK n`(n>0일 때만)을 낸다. 커버리지 감사가 화면 반대 사실을
   주입하는 경로가 이번 실패의 2번 원인이므로 이 관문은 반드시 감사 경로에도 걸려야 한다.
5. **K type 정규화**(지난 라운드 미해결): K의 type이 enum 밖이면 드롭 대신 별칭 정규화
   (`*-setting`·`config`→`setting`, `step`→`procedure`, `tip`·`note`→`warning`, 그 외→`concept`)
   하고 기존 `NORMALIZED` 집계에 포함. 실측 사례: 커버리지가 `font-setting`·`layout-setting`을
   내 배치 전량 거부 → 왕복 1회.

**테스트**(실측 픽스처 회귀): 25↔30 사례 그대로 → flag 1건·screen_conflict 표기·본문 불변,
창 밖 V는 무시, 창에 V 없으면 무flag, `$25`처럼 자막 유래 수치가 setting이 아니면 무flag,
K type 별칭 5종 정규화, SCREENCHECK 0건이면 stdout 미출현.

---

### Task B: 근거 인용 감지·재합성 + 합성 계약 (프롬프트) — 병렬 가능
**Files:** skills/tuto/SKILL.md, skills/tuto/prompts/synthesize.md,
tests/test_skill_contract.py(append), tests/test_prompt_contract.py(append)

1. **synthesize.md 최종 응답 계약에 `V 인용 j건` 추가**(현행 `V 복사 m건`과 별도 — 이번 실패는
   복사 10·인용 0이었고, 두 숫자를 함께 받아야 본체가 감지할 수 있다).
2. **synthesize.md 계약 강화**: "화면에서 읽은 **구체값**(설정값·UI 라벨·수치·파일명)은 자막이
   말하지 않아도 K로 등재하고 `v#`로 인용하라 — 따라하려면 필요한 값이다. 자막값과 화면값이
   다르면 **화면을 채택**하고 `conflict=자막값=>화면값`." (기존 화면 우선 규칙이 실효가 없었으니
   구체값 등재 의무를 명시한다.) **하한을 자막만으로 채우지 마라**도 한 줄.
3. **SKILL 5단계 감지·재합성**: 합성 응답의 `V 인용 j건`이 **0인데 vision-*.lines에 V 관측이
   10줄 이상이면** 같은 디스패치를 **1회만** 재시도(지시에 '화면 근거 미인용 감지 — 화면 구체값을
   K로 등재하고 v# 인용' 추가). 재시도 후에도 0이면 진행하되 8단계 `--note "화면 근거 미인용"`.
   빈약 전사 감지와 동형(이미 2회 검증된 패턴). 자수 예산 빠듯하니 문장을 아껴라.

**테스트**: 계약 문구 단언(응답 형식·구체값 등재·감지 임계 10·1회 상한·note).

---

### Task C (controller): v0.19.0 배포 → 회귀 게이트
`pwGeWRlrU10` 재실측 — **통과 조건**: ① frame 인용 K ≥1 ② Size 값이 25로 실리거나
`screen_conflict`/`conflict=`로 표기 ③ 부풀리기 0 ④ ≤$2.8. 예산 $3.5, 2연속 실패 시 보류.
