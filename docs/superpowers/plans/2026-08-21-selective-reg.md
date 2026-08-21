# 선별 등재 (selective registration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** 하류 곱수 제거 — 검수(읽기)는 현행 전량, **정본 등재는 문서가 인용한 관측만**. + dense 브랜치의 관용 계약 이식. 게이트: kYPAlvnRiiI(20:04) ≤$3.0(현행 $5.17), 지식 유지율 ≥85%, 날조 0.

**헌장(사용자 승인):** Phase 0 정찰이 A 프로파일 전제를 반증(실사용 영상 전부 자막 있는 튜토리얼 계열, 비용 변수는 유형이 아니라 화면 텍스트 밀도) → 보편 레버로 피벗. 잔여 예산 $4.7, 게이트 2연속 실패 시 자동 보류, 사용자 개입은 최종 판정 1회.

**스케일 프리모템:** 변하는 수치 = 등재 V(155→인용분 ~50-70). 그 수치를 가정하는 계약 = ① 교차 대조(등재 V만 보게 됨 — 인용 증거 간 충돌만 잡는 것으로 계약 축소, 재확인 디스패치는 관용 정책으로 어차피 폐지) ② 후속 질문 캐시 재질의(정본에 없는 관측 → vision-*.lines 지연 로딩 절 신설) ③ id_offset(드롭 결번 시 len() 버그 — dense에서 발견, **이번에 수정 필수**).

## Global Constraints
- 짧은 영상 동작 회귀 금지(계약 테스트 보장), SKILL <7,000자·프롬프트 <3,500자.
- 테스트 append-only(예외: 재확인 디스패치·V 전부 복사 관련 기존 단언 — 사전 선언, 커밋 메시지 나열).
- 관용 계약의 원본은 dense 브랜치(커밋 8346d04·8678bbd) — 필요분만 이식(F-헤더는 이번 범위 밖).
- Windows python, pytest exit 가리지 않기, Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>.

### Task 1 (code): evidence.py 관용 이식 + id_offset 수정
- V 관용 드롭+`DROPPED n` stdout(전량 거부 폐지, K/C는 20% 임계 게이트) — dense 브랜치 구현을 참조해 master 코드베이스에 이식(하위호환: 단일/기존 파일 경로 무변경).
- id_offset을 len() 기반 → **기존 v-id 최대 숫자+1**로(드롭 결번 대비). 회귀 테스트: 결번 있는 evidence에 후속 배치 병합.
- 테스트: dense 브랜치의 관용 테스트를 이식·적응 + 결번 케이스.

### Task 2 (docs): 선별 등재 배선
- synthesize.md: "V 전부 복사" → "**인용 V만 복사** — K/C가 refs로 참조하는 V만 patch에 옮긴다(v#는 patch 내 등장 순서). 인용하지 않은 관측은 옮기지 않는다 — 원본 vision-*.lines가 캐시에 남는다." 보강 모드도 동일 원칙.
- SKILL.md: ① 합성 단계 문구 갱신 ② 병합 단계에 "stdout의 DROPPED n을 8단계 --note '형식 드롭 n건'으로 보고, INVALID(20% 초과)만 1회 재전달" ③ 6단계 재확인 디스패치 제거 — flag는 --cross-flags 기록만(관용 정책: 최근 flag 10건 전부 오탐 실측) ④ 후속 질문 절에 지연 로딩: "정본에 없는 관측을 물으면 해당 vision-*.lines(캐시 보존)를 그때 Read".
- 계약 테스트: 인용 V만·DROPPED 보고·재확인 미디스패치·지연 로딩 문구 + 기존 충돌 단언 정리(선언).

### Task 3 (controller): 게이트
- v0.13.0 범프·배포 → 2분 영상(nHcfoHOW4uA) 통합 게이트(~$0.5): 완주·DROPPED 보고 경로 확인 → kYPAlvnRiiI 재실측 1회: **≤$3.0·지식 ≥44건(85%)·날조 0(fable 프레임 대조 3건)·evidence V가 인용분만인지 확인**. 실패 시 1회 수정 후 재도전, 2연속 실패면 자동 보류(헌장).
