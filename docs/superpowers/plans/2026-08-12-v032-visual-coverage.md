# v0.3.2 — visual coverage 사각지대 제거 + 평가 단계 진입 (최소 변경 플랜)

**Goal:** 빌더의 구식 audit 후보 계약을 걷어내고, **화면에만 있는 정보의 누락**을 커버리지 감사가 감지하게 만든다. 그리고 실제 영상 평가 프로토콜을 문서화한다.

**Non-goal:** 아키텍처 확장. 두 번째 vision pass 추가. MCP·Web UI·DB.

---

## 설계 판단

### 1. visual coverage는 §2 판독 에이전트가 만든다 (Option A)

§2는 **이미 지도 프레임을 전부 읽고 있다.** 거기서 관측을 함께 뽑으면 **추가 이미지 판독 비용이 0**이다. 새 vision pass를 만들면 안 되는 이유가 이것이다.

> Do not add another video analysis pipeline just to check the first one.

**독립성도 확보된다** — 빌더가 evidence를 만들고, 판독 에이전트가 coverage source를 만든다. 같은 LLM이 "무엇을 뽑을지"와 "무엇이 빠졌는지"를 둘 다 정하면 독립성이 없다.

```
판독 에이전트 → visual-coverage.json  (존재 신호)
빌더          → evidence.json         (정확한 값)
커버리지 감사 → 둘을 대조
```

### 2. `visual-coverage.json`은 별도 산출물이다 — evidence.json에 넣지 않는다

관측은 **검증되지 않은 존재 신호**다. 정본인 evidence.json에 섞으면 "근거"와 "힌트"의 경계가 무너진다. 캐시 디렉토리의 중간 산출물로 둔다.

### 3. kind는 기존 상수를 재사용한다

`OBSERVATION_KINDS = KNOWLEDGE_TYPES + ("numeric", "other")` — 13종. 새 온톨로지를 만들지 않고, 커버리지 대조가 `kind ↔ knowledge type`으로 직접 이어진다.

### 4. 관측의 목적은 값 판독이 아니라 존재 확인

`CUDA 12.6`을 정확히 옮길 필요 없다. `"CUDA/버전 설정 화면 보임"`이면 충분하다. 정확한 값은 빌더·targeted zoom이 담당한다.

---

## Task 1: SKILL.md §4 구식 계약 제거

`skills/tuto/SKILL.md:313,317`

- [ ] 4단계("표본 주장 후보 6건 반환") **삭제**. 빌더 책임을 3개로 축소: patch 생성 → 검증 통과 → video.md 작성
- [ ] 계약 위반 조건에서 "후보 미반환" 제거 (불필요한 retry 유발)
- [ ] §5에 후보 선정은 `--audit-candidates`가 한다고 이미 적혀 있음 — 중복 제거만
- [ ] `tests/test_skill_contract.py`에 회귀 테스트 추가: 구식 계약 문구가 다시 들어오면 실패

## Task 2: evidence.py — 관측 스키마·검증·대조

`skills/tuto/scripts/evidence.py`

**Produces:**
- `OBSERVATION_KINDS`
- `load_observations(cache_dir) -> list`
- `validate_observations(obs, ev) -> list[str]` — kind 열거형 · frame provenance 실재성 · timestamp 숫자
- `uncovered_observations(ev, obs, window=45.0) -> list` — **결정론적 사전 필터**
- `coverage_input(ev, obs) -> str` — 커버리지 감사 입력 블록
- CLI `--coverage-input <visual-coverage.json>`

**`uncovered_observations` 규칙:** 관측 시각 ±`window`초 안에 **같은 kind의** knowledge_item이 없으면 후보. `numeric`·`other`는 kind 무관하게 아무 항목이나 있으면 covered로 본다(과잉 후보 방지).

이건 **힌트지 판정이 아니다** — 최종 판단은 커버리지 감사 LLM이 한다.

## Task 3: SKILL.md §2·§5 연결

- [ ] §2 산출 계약에 `visual-coverage.json` 추가 (반환 4줄은 유지, 파일만 하나 더)
- [ ] §5 커버리지 감사 입력에 관측 추가, 프롬프트에 "존재 신호이지 값의 정본이 아니다" 명시
- [ ] 감사 스탬프 문구를 `claims + knowledge_items` 기준으로 수정

## Task 4: 테스트

- [ ] 관측 스키마: 정상 accept / 알 수 없는 kind reject / 없는 프레임 reject / timestamp 누락 reject
- [ ] **핵심**: 관측에 `command`가 있는데 digest에 해당 시각 command가 없으면 후보로 잡히는지
- [ ] 같은 kind가 window 안에 있으면 후보가 아님
- [ ] 기존 199 테스트 유지

## Task 5: 문서 정리

- [ ] **README `Step recall` 원래 의미 복원** — v0.3.1에서 내가 "expected knowledge items"로 바꾼 것은 측정 재수행 없는 재해석이었다. `Tutorial step recall (R1)`로 되돌린다
- [ ] `metadata and guides are preserved` → `metadata, evidence.json, and video.md are preserved`
- [ ] README coverage 설명에 visual observation 추가
- [ ] evidence.json 예시에 `knowledge_items` 추가
- [ ] `docs/eval/pipeline.md`에 visual-coverage 위치 설명 (evidence 스키마에 넣지 않는 이유 포함)

## Task 6: 평가 프로토콜

`docs/eval/real-world-eval.md` — 복잡한 프레임워크 없이 반복 가능한 절차만.

- 영상 카테고리 8~10종, URL + 타임스탬프 + 사람 확인 ground truth만 저장(영상 파일 저장 안 함)
- 평가 축 4개: Understanding/coverage · Factual faithfulness · Source traceability · **Agent usefulness**
- 실행형은 **sandbox/fixture 프로젝트에서만**. `sudo`·레지스트리·`curl|bash`·삭제는 제외
- 보고 템플릿
- **아직 측정하지 않은 수치를 README에 올리지 않는다**는 규칙 명시

## Task 7: E2E

- [ ] UI-heavy 튜토리얼(`PlMpk-If9jA`)로 §2 관측 생성 → 대조
- [ ] **핵심 시나리오**: 화면에만 있는 항목을 digest에서 의도적으로 뺀 fixture로 후보 검출 확인
