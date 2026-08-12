# 실사용 평가 프로토콜 (v1)

**평가하려는 것:** *"사람이 영상을 보지 않은 상태에서 AI가 그 영상을 충분히 이해했는가?"*

영상 요약 품질을 재는 게 아니다. 호출한 에이전트가 그 지식으로 **설명·비교·적용·실행**을 할 수 있는지를 본다.

> **사용자는 영상을 끝까지 안 볼 수 있다. 화면에만 있던 중요한 정보를 놓치는 것은 사소한 누락이 아니라 1급 실패다.**

복잡한 벤치마크 프레임워크를 만들지 않는다. 반복 가능한 절차와 보고 양식만 둔다.

---

## 저장 규칙

**영상 파일·자막·프레임을 저장소에 넣지 않는다.** 저작권 문제도 있고 저장소가 무거워진다.
남기는 것은 이것뿐이다:

- 공개 YouTube **URL**
- **타임스탬프**
- 사람이 확인한 **ground truth 항목**
- 평가 결과 보고서

비공개·미등록 영상은 fixture로 쓰지 않는다.

---

## 평가 영상 카테고리

한 유형당 1편, 총 8~10편을 목표로 한다. **화면 정보 밀도가 서로 다른 유형을 섞는 것**이 핵심이다.

| # | 유형 | 이 유형에서 특히 보는 것 |
|---|---|---|
| 1 | 개발환경 설치 튜토리얼 | prerequisite · setting · criterion |
| 2 | 코딩 튜토리얼 | command · code · procedure 순서 |
| 3 | AI 도구 사용법 | setting · action · 화면 전용 값 |
| 4 | UI 조작 위주 설정 튜토리얼 | 버튼명 · 체크박스 상태 · 메뉴 항목 |
| 5 | 터미널/CLI 위주 | command 정확도 · 출력 판독 |
| 6 | 강의 / 개념 설명 | concept · example · 억지 절차 생성 여부 |
| 7 | 슬라이드 발표 | 수치 · 표 · claim |
| 8 | 제품 데모 | 기능 · 워크플로 · 한계 |
| 9 | 화면 + 내레이션 혼합 | 자막↔화면 역할 분담 |
| 10 | **자막과 화면 값이 다른 영상** | `conflict` 검출 |

기존 회귀 영상을 재사용해도 된다. 다만 **골든셋과 평가셋을 섞지 않는다** — 골든셋은 회귀 기준이고 평가셋은 실사용 진단이다.

---

## 평가 축 4개

### A. Understanding / coverage

사람이 원본 영상을 보고 만든 체크리스트와 대조해 **중요 지식 재현율**을 본다.

범주: `concept` `procedure` `action` `command` `setting` `prerequisite` `result` `criterion` `warning` `중요 수치`

**영상에 존재하는 범주만 평가한다.** 인터뷰에 `command`가 없는 건 결함이 아니다.

### B. Factual faithfulness

명령어 · 버전 · 버튼명 · 설정값 · 수치 · 화면 텍스트 · 순서가 맞는가.

**화면에만 있던 정보를 따로 표시한다** — 이 프로젝트의 차별점이 거기 있으므로 별도 집계가 필요하다.

### C. Source traceability

추출된 중요 항목이 실제로 `timestamp` · `frame` · `transcript segment`로 추적 가능한가.

`evidence.py --validate`가 구조적 무결성은 잡지만, **근거가 정말 그 내용을 담고 있는지**는 사람이 표본으로 확인한다.

### D. Agent usefulness ← **가장 중요**

사람이 영상을 **보지 않은 상태에서** 에이전트에게 시킨다.

```text
/tuto <url> 이 내용을 나한테 가르쳐줘
```

평가: 핵심을 이해했나 · 중요한 예/수치/절차가 빠졌나 · **영상에 없는 걸 지어냈나**

튜토리얼이면 추가로:

```text
/tuto <url> 이걸 현재 테스트 프로젝트에 적용해줘
```

평가: prerequisite를 확인했나 · 올바른 명령/설정을 썼나 · **환경 차이를 감지했나** · 성공 조건을 확인했나 · **영상 방법을 맹목적으로 복사하지 않았나**

---

## 실행형 평가의 안전 규칙

**샌드박스에서만 한다.**

허용: 임시 디렉토리 · fixture 저장소 · 일회용 virtualenv · 로컬 테스트 프로젝트

**자동 E2E에서 제외하거나 목(mock)으로 대체:**

```
sudo · 레지스트리 편집 · OS 설정 변경 · 실제 클라우드 과금
실제 자격증명 · curl | bash · 삭제 위험 작업
```

이런 조작이 필수인 영상은 **A~C까지만 평가하고 D의 실행 부분은 건너뛴다.** 억지로 실행하지 않는다.

---

## 실행 절차

```bash
# 1. 분석
/tuto <url>

# 2. 구조 무결성
python skills/tuto/scripts/evidence.py <cache_dir> --validate

# 3. 지식 목록 (사람 체크리스트와 대조)
python skills/tuto/scripts/evidence.py <cache_dir> --digest

# 4. 커버리지 사각지대 (화면 전용 정보 누락)
python skills/tuto/scripts/evidence.py <cache_dir> --coverage-input

# 5. 고위험 항목 감사 대상
python skills/tuto/scripts/evidence.py <cache_dir> --audit-candidates 6

# 6. 비용
python docs/eval/measure-cost.py --marker <video_id>
```

---

## 보고 양식

`docs/eval/reports/<video_id>.md`로 남긴다.

```markdown
# Video Evaluation — <video_id>

URL:
Type:
Duration:
Pipeline version:

## Human Ground Truth
(사람이 영상을 보고 만든 체크리스트 — 범주별)

## Extracted Knowledge
(--digest 결과 요약)

## Missed
(체크리스트에 있는데 evidence에 없는 것)

## Incorrect
(evidence에 있는데 틀린 것)

## Screen-only facts
- expected:
- recovered:
- (놓쳤다면 visual observation은 있었는가? → 커버리지 감사가 잡을 수 있었는가?)

## Audit results
(표본 감사 N건 중 일치/수정)

## Coverage results
(누락 후보 N건 → 확인 결과)

## Agent task
Prompt:
Result:
(D축 평가 — 사람 판단)

## Verdict
PASS / PARTIAL / FAIL

## Regression note
(다음 라운드에서 봐야 할 것)
```

**자동 계산 가능한 것과 사람 판단을 구분해 적는다.** A·B의 개수 집계는 자동이지만 "충분히 이해했는가"는 사람 판단이다.

---

## 수치 공개 규칙

**측정하지 않은 수치를 README에 올리지 않는다.**

현재 공개된 지표는 **튜토리얼 골든셋(3~5편)** 기준이며 그 범위를 벗어난 주장을 하지 않는다:

- `Tutorial step recall (R1) 0.913` — 튜토리얼 골든셋의 스텝/행동 재현율
- `Value F1 0.909` — 같은 셋의 값 정확도
- 환각 값 0건

`knowledge_items` 전체에 대한 recall을 주장하려면 **이 프로토콜로 별도 측정**해야 한다.
제품 방향이 바뀌었다고 기존 숫자의 의미를 재해석하지 않는다 —
실제로 v0.3.1에서 `expected steps` → `expected knowledge items`로 라벨만 바꿨다가 되돌린 적이 있다.

`agent execution success 95%` 같은 수치는 **D축을 실제로 여러 편 돌린 뒤에만** 공개한다.

---

## 이 프로토콜을 언제 돌리나

- 파이프라인 계약(SKILL.md §2·§4·§5)이 바뀔 때
- 새 영상 유형을 지원한다고 주장할 때
- 릴리스 전

라운드마다 전부 돌릴 필요는 없다. **유형이 다른 2~3편**이면 회귀 진단에 충분하다.
